import Adafruit_MPR121.MPR121 as MPR121
import cv2
import itertools
import math
import random
import numpy as np
import sys

X_RES = 192
Y_RES = 108
NUM_X = 8
NUM_Y = 4
COV_MULT = 0.1

DEBUG_TOUCH = False
DEBUG_IMAGE = False
DEBUG_CENTERS = False

EMPTY_TOUCH_STATE = [0,0,0,0,0,0,0,0,0,0,0,0]

IMAGE_NAME = "rendering"

class Vertex:

    def __init__(self, x, y):
        self.x = max(0, min(X_RES, x))
        self.y = max(0, min(Y_RES, y))
        self.age = 0

    def advanceAge(self, amount = 1):
        self.age += amount
        self.age = min(50,max(0, self.age))

    def alive(self):
        return (self.age > 0)

class Position:

    # x/y are in pixels from bottom left
    def __init__(self, x, y, vert_index, horiz_index):
        self.x = x
        self.y = y
        self.vert_index = vert_index
        self.horiz_index = horiz_index
        self.on = False;
        self.vertices = []

    def update(self, cap_state):
        update_val = 0
        if cap_state[self.vert_index] and cap_state[self.horiz_index]:
            self.on = True
            update_val = 1
        else:
            self.off = False
            update_val = -1

        # add random position if there are no more than 5 point
        if (len(self.vertices) < 5):
            self.vertices.append(self.getRandomVertex())

        # inefficient copy version, but safer
        new_vertices = []
        for v in self.vertices:
            v.advanceAge(update_val)
            if (v.alive()):
                new_vertices.append(v)

        self.vertices = new_vertices

    def getRandomVertex(self):
        cov = COV_MULT * (X_RES+Y_RES)/2.0
        rand_vertex = Vertex(int(random.normalvariate(self.x, cov)),
                             int(random.normalvariate(self.y, cov)))
        return rand_vertex

class ScreenState:

    def __init__(self):
        self.positions = self.createPositions()
        self.color = (0,0,255)
        self.edge_pos = (0,0)
        self.edge_direction = (1,0)
        self.color_bkgnd = np.zeros((Y_RES, X_RES, 3), np.uint8)

    def createPositions(self,
                        x_width = X_RES,
                        y_width = Y_RES,
                        num_x = NUM_X,
                        num_y = NUM_Y):
        positions = []
        for (x_index, y_index) in list(itertools.product(range(0,num_x), range(num_x,num_x+num_y))):
            x_pos = (x_index+0.5) * (x_width/(num_x))
            y_pos = (y_index-num_x+0.5) * (y_width/(num_y))
            new_pos = Position(x_pos, y_pos, x_index, y_index)
            positions.append(new_pos)
        return positions

    def updatePositions(self, touch_state):
        # got through positions and update them
        map (lambda p : p.update(touch_state), self.positions)

    def renderScreen(self):
        screen = np.zeros((Y_RES, X_RES,3), np.uint8)
        # draw a circle on every vertex w/ a size proportional to it's age
        poly_points = []
        for p in self.positions:
            if (DEBUG_CENTERS):
                cv2.circle(screen, (int(p.x), int(p.y)), 1, (255,255,255), -1)
            for v in p.vertices:
                cv2.circle(screen, (v.x, v.y), v.age*10, (255,255,255), -1)
                poly_points.append([v.x,v.y])
        # also draw some polygons
        if len(poly_points) > 1:
            cv2.fillPoly(screen, [np.array(poly_points)], (255,255,255))

        return cv2.bitwise_and(screen,self.color_bkgnd)

    def updateBackground(self):
        # rotate pos
        self.edge_pos = (self.edge_pos[0] + self.edge_direction[0],
                        self.edge_pos[1] + self.edge_direction[1])

        if (self.edge_pos == (X_RES,0)):
            self.edge_direction = (0,1)
        elif (self.edge_pos == (X_RES,Y_RES)):
            self.edge_direction = (-1,0)
        elif (self.edge_pos == (0,Y_RES)):
            self.edge_direction = (0,-1)
        elif (self.edge_pos == (0,0)):
            self.edge_direction = (1,0)

        other_pos = (X_RES - self.edge_pos[0], Y_RES - self.edge_pos[1])
        self.color_bkgnd = np.zeros((Y_RES, X_RES, 3), np.uint8)

        self.color_bkgnd[:,:,0].fill(255)
        self.color_bkgnd[:,:,1].fill(212)
        self.color_bkgnd[:,:,2].fill(128)

        cv2.circle(self.color_bkgnd, self.edge_pos, 70, (20*2,86*2,252*2), -1)
        cv2.circle(self.color_bkgnd, other_pos, 70, (255*2,64*2,233*2), -1)
        self.color_bkgnd = cv2.GaussianBlur(self.color_bkgnd, (101,101), 20)

class PolyPillowEmoter:

    def __init__(self):
        self.state = ScreenState()
        self.mouse_touch_state = list(EMPTY_TOUCH_STATE)
        self.mouse_down = False
        if (not DEBUG_TOUCH):
            # Create MPR121 instance.
            self.cap = MPR121.MPR121()
            
            # Initialize communication with MPR121 using default I2C bus of device 
            if not self.cap.begin():
                print 'Error initializing MPR121.  Check your wiring!'
                sys.exit(1)

    def mouseCallback(self, event, x, y, flags, param):
        if (event == cv2.EVENT_LBUTTONUP):
            self.mouse_touch_state = list(EMPTY_TOUCH_STATE)
            self.mouse_down = False
        elif (event == cv2.EVENT_LBUTTONDOWN or self.mouse_down):
            self.mouse_down = True
            # bin the position into the right regions using a search
            closest_distance = -1
            closest_point = []
            for p in self.state.positions:
                this_distance = math.sqrt((x - p.x)**2 + (y - p.y)**2)
                if closest_distance == -1 or this_distance < closest_distance:
                    closest_distance = this_distance
                    closest_point = p
            closest_touch_state = list(EMPTY_TOUCH_STATE)
            closest_touch_state[closest_point.vert_index] = 1
            closest_touch_state[closest_point.horiz_index] = 1
            self.mouse_touch_state = closest_touch_state

    def getTouchState(self):
        # read touch state from MPR121 or mouse for debug
        if (DEBUG_TOUCH): #use mouse
            return self.mouse_touch_state
        else: #use MPR121
            current_pins_touched = self.cap.touched()
            cap_touched = list(EMPTY_TOUCH_STATE)
            for i in range(12):
                pin_bit = 1 << i
                if (current_pins_touched & pin_bit):
                    cap_touched[i] = 1
            return cap_touched

    def updatePolygons(self, touch_state):
        self.state.updatePositions(touch_state)

    def show(self):
        img = self.state.renderScreen()
        cv2.imshow(IMAGE_NAME,img)
        cv2.waitKey(10)

    def adjustColors(self):
        self.state.updateBackground()

    def run(self):
        if (DEBUG_IMAGE):
            cv2.namedWindow(IMAGE_NAME)
        else:
            cv2.namedWindow(IMAGE_NAME, cv2.WND_PROP_FULLSCREEN)
            cv2.setWindowProperty(IMAGE_NAME, cv2.WND_PROP_FULLSCREEN, cv2.cv.CV_WINDOW_FULLSCREEN)
        cv2.setMouseCallback(IMAGE_NAME, self.mouseCallback)

        while (True):
            # Get current touch state
            touch_state = self.getTouchState()
            # Apply touch state to polygon filler
            self.updatePolygons(touch_state)

            # Cycle Colors
            self.adjustColors()

            # Display
            self.show()

if __name__ == '__main__':
    emoter = PolyPillowEmoter()
    emoter.run()