"""
Input handling scheme.

An operation that can be performed in response to user input is an Action. Different
inputs are mapped to actions in tables held by an InputHandling object.

While the keybindings are presently hard coded, the way mappings are represented
could easily be saved out and read back in, allowing for full customisation.

The scheme allows for keyboard, mouse and joystick input.
"""

from pymunk.vec2d import Vec2d

import pygame
import collections

from .components import Thrusters, Player, Camera, Turrets, Turret
from .direction_providers import DirectionProviderScreen

class InputResponse(object):
    """ The result of executing an Action.  This is bubbled back up to the
    main loop which can decide what to do - perhaps halt the program. """
    def __init__(self):
        self.quit_requested = False
        self.event_handled = False


class Action(object):
    """ An action in response to an input.  Tables of actions are used to
    respond to input events. 
    
    An action can be called in response to different types of inputs.  A button
    press will call execute(), which takes an input that stipulates whether the
    button is going up or down.  execute_position() is similar, but has a
    position as well - for instance, a mouse click will have this information.
    Finally some inputs are continuous; these will result in the execute_position()
    function being called.
    
    The more complex execute_*() by default call down to the basic execute(),
    meaning that a simple action can be bound to any type of input.   A more
    specialised action that only makes sense in response to continuous input
    might do nothing in response to execute().
    """

    def __init__(self, description):
        """ Constructor. """
        assert description is not None
        self.description = description

    def execute(self, alternate):
        """ Execute the action. If 'alternate' is true then an 'alternate'
        action should be performed - for instance if this action is handling
        a keyboard key, the 'keydown' even will execute with alternate=False,
        while the 'keyup' event will have alrenate=True, but both will be mapped
        to the same Action object. """
        return InputResponse()

    def execute_position(self, position, alternate):
        """ Execute with a position input.  The default implementation calls
        the regular execute(). """
        return self.execute(alternate)

    def execute_linear(self, value):
        """ Execute with a linear input.  The default implementation calls
        the regular execute(). """
        return self.execute(True)


class FuncAction(Action):
    """ An action that will execute one of two handler functions. 
    
    This will typically be used for actions that correspond naturally to key
    presses e.g. 'pause the game'.
    """

    def __init__(self, description, f1, f2 = None):
        """ Constructor.  If a single argument is supplied, then execute() will
        do nothing unless ***alternate==TRUE***.  This is useful for instance
        when something should only be done in response to a key UP event. """
        assert description is not None
        assert f1 is not None
        Action.__init__(self, description)
        if f2 is not None:
            self.__f1 = f1
            self.__f2 = f2
        else:
            def nothing(): pass
            self.__f1 = nothing
            self.__f2 = f1

    def execute(self, alternate):
        """ Execute our handler function. """
        ret = None
        if not alternate:
            ret = self.__f1()
        else:
            ret = self.__f2()
        if ret is None:
            ret = InputResponse()
            ret.event_handled = True
        return ret


class ShootAction(Action):
    """ An action to start shooting. """

    def __init__(self, description, handler):
        """ Constructor. """
        Action.__init__(self, description)
        self.handler = handler

    def execute_position(self, position, alternate):
        """ Start shooting at the given point. """
        if not alternate:
            self.handler.start_shooting(position)
        else:
            self.handler.stop_shooting()
        ret = InputResponse()
        ret.event_handled = True
        return ret

    def execute_linear(self, value):
        """ Keep looking in the right direction. """
        self.handler.maintain_aim(value)
        ret = InputResponse()
        ret.event_handled = True
        return ret


class Actions(object):
    """ A table of actions. """

    def __init__(self, handler):
        """ Constructor.  Create the actions. """

        # Directions.
        forwards = Vec2d(0, -1)
        backwards = Vec2d(0, 1)
        left = Vec2d(-1, 0)
        right = Vec2d(1, 0)
        turn_left = 1
        turn_right = -1

        # A function to request the program halt.
        def quit():
            ret = InputResponse()
            ret.event_handled = True
            ret.quit_requested = True
            return ret

        # Handlers
        self.MOVE_FORWARDS = FuncAction("Move forwards",
                                        lambda: handler.move(forwards),
                                        lambda: handler.move(backwards))
        self.MOVE_BACKWARDS = FuncAction("Move backwards",
                                         lambda: handler.move(backwards),
                                         lambda: handler.move(forwards))
        self.MOVE_LEFT = FuncAction("Move left",
                                    lambda: handler.move(left),
                                    lambda: handler.move(right))
        self.MOVE_RIGHT = FuncAction("Move right",
                                     lambda: handler.move(right),
                                     lambda: handler.move(left))
        self.ROTATE_CLOCKWISE = FuncAction("Rotate clockwise",
                                           lambda: handler.turn(turn_right),
                                           lambda: handler.turn(turn_left))
        self.ROTATE_ANTICLOCKWISE = FuncAction("Rotate anticlockwise",
                                               lambda: handler.turn(turn_left),
                                               lambda: handler.turn(turn_right))
        self.ZOOM_IN = FuncAction("Zoom in",
                                  lambda: handler.zoom_in())
        self.ZOOM_OUT = FuncAction("Zoom out",
                                   lambda: handler.zoom_out())
        self.QUIT = FuncAction("Quit", quit)
        self.SAVE = FuncAction("Save",
                               lambda: handler.game_services.save())
        self.LOAD = FuncAction("Load",
                               lambda: handler.game_services.load())
        self.TOGGLE_PAUSE = FuncAction("Pause / unpause",
                                       lambda: handler.game_services.toggle_pause())
        self.STEP = FuncAction("Simulate one frame then pause",
                               lambda: handler.game_services.step())
        self.SHOW_KEYS = FuncAction("Show keys",
                                    lambda: handler.print_keybindings())
        self.SHOOT = ShootAction("Shoot", handler)


class KeyMap(object):
    """ A mapping from keys to actions. """

    def __init__(self, name, mapping):
        """ Constructor. 'mapping' should be a dict-like mapping from keys
        to actions to be executed. """
        self.__name = name
        self.__mapping = mapping

    def execute(self, key, alternate):
        """ If this key is mapped to an action, execute the corresponding action
        and return the response. """
        if key in self.__mapping:
            return self.__mapping[key].execute(alternate)
        return InputResponse()

    def execute_position(self, key, position, alternate):
        """ If this key is mapped to an action, execute the corresponding
        action and return the response. """
        if key in self.__mapping:
            return self.__mapping[key].execute_position(position, alternate)
        return InputResponse()

    def execute_linear(self, key, value):
        """ If this key is mapped to an action, execute the corresponding
        action and return the response. """
        if key in self.__mapping:
            return self.__mapping[key].execute_linear(value)
        return InputResponse()

    def print_keybindings(self, key_display_func):
        """ Print out the key bindings. """
        if len(self.__mapping) == 0:
            return
        print ""
        print self.__name
        print "-" * len(self.__name)
        print ""
        for key in sorted(self.__mapping):
            print "    " + key_display_func(key) + ": " + self.__mapping[key].description


class InputHandling(object):
    """ Handles input. """

    def __init__(self, view, game_services):
        """ Initialise. """

        # Provides access to the bits of the game we want to manipulate.
        self.game_services = game_services

        # The view.
        self.__view = view

        # Initialse pygame's joystick functionality
        pygame.joystick.init()
        self.js = None
        if pygame.joystick.get_count() > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()

        # The actions table.
        self.__actions = Actions(self)

        # Keyboard controls.
        self.__kmap = KeyMap("Keyboard", {
            pygame.K_w: self.__actions.MOVE_FORWARDS,
            pygame.K_a: self.__actions.MOVE_LEFT,
            pygame.K_s: self.__actions.MOVE_BACKWARDS,
            pygame.K_d: self.__actions.MOVE_RIGHT,
            pygame.K_q: self.__actions.ROTATE_CLOCKWISE,
            pygame.K_e: self.__actions.ROTATE_ANTICLOCKWISE,
            pygame.K_t: self.__actions.ZOOM_IN,
            pygame.K_g: self.__actions.ZOOM_OUT,
            pygame.K_ESCAPE: self.__actions.QUIT,
            pygame.K_F8: self.__actions.SAVE,
            pygame.K_F9: self.__actions.LOAD,
            pygame.K_PAUSE: self.__actions.TOGGLE_PAUSE,
            pygame.K_BACKQUOTE: self.__actions.STEP,
            pygame.K_F11: self.__actions.SHOW_KEYS,
        })

        # Joystick (button) controls.
        self.__js_map = KeyMap("Joystick buttons", {
            4: self.__actions.ROTATE_CLOCKWISE,
            5: self.__actions.ROTATE_ANTICLOCKWISE,
        })

        # Joystick (axis) controls.
        self.__js_axis_map = KeyMap("Joystick axes", {})

        # Joystick (ball) controls.
        self.__js_ball_map = KeyMap("Joystick balls", {})

        # Joystick (hat) controls.
        self.__js_hat_map = KeyMap("Joystick hats", {})

        # Mouse controls.
        self.__mouse_map = KeyMap("Mouse", {
            1: self.__actions.SHOOT,
            4: self.__actions.ZOOM_IN,
            5: self.__actions.ZOOM_OUT,
        })

        # Mouse motion.
        self.__mouse_motion_map = KeyMap("Mouse motion", {
            1: self.__actions.SHOOT
        })

        self.__zoom_increment = 0.03

        self.__shooting = False

    def print_keybindings(self):
        """ Output the keybindings. """
        for map in (self.__kmap,
                    self.__mouse_map,
                    self.__js_map,
                    self.__js_hat_map,
                    self.__js_axis_map,
                    self.__js_ball_map):
            key_display_func = lambda x: str(x)
            if map == self.__kmap:
                key_display_func = pygame.key.name
            map.print_keybindings(key_display_func)

    def handle_input(self, e):
        """ Dispatch a pygame input event to the relevant key mapping table
         and return the response. """

        if e.type == pygame.QUIT:
            # Quit requested from window manager.
            return self.__actions.QUIT.execute(True)
        elif e.type == pygame.KEYDOWN or e.type == pygame.KEYUP:
            return self.__kmap.execute(e.key, e.type == pygame.KEYUP)
        elif e.type == pygame.MOUSEMOTION:
            ret = InputResponse()
            ret.event_handled = True
            for button in e.buttons:
                ret1 = self.__mouse_motion_map.execute_linear(button, e.pos)
                if ret1.event_handled == True:
                    ret = ret1
            return ret
        elif e.type == pygame.MOUSEBUTTONDOWN or e.type == pygame.MOUSEBUTTONUP:
            return self.__mouse_map.execute_position(e.button,
                                                     e.pos,
                                                     e.type == pygame.MOUSEBUTTONUP)
        elif e.type == pygame.JOYAXISMOTION:
            return self.__js_axis_map.execute_linear(e.axis, e.value)
        elif e.type == pygame.JOYBALLMOTION:
            return self.__js_axis_map.execute_linear(e.ball, e.rel)
        elif e.type == pygame.JOYBUTTONDOWN or e.type == pygame.JOYBUTTONUP:
            return self.__kmap.execute(e.button, e.type == pygame.JOYBUTTONUP)
        elif e.type == pygame.JOYHATMOTION:
            return self.__js_hat_map.execute_linear(e.hat, e.value)

        return InputResponse()

    def zoom_in(self):
        """ Zoom the camera in."""
        cameras = self.game_services.get_entity_manager().query(Camera)
        for camera in cameras:
            camera.get_component(Camera).zoom += self.__zoom_increment

    def zoom_out(self):
        """ Zoom the camera out. """
        cameras = self.game_services.get_entity_manager().query(Camera)
        for camera in cameras:
            c = camera.get_component(Camera)
            c.zoom -= self.__zoom_increment
            if c.zoom <= self.__zoom_increment:
                c.zoom = self.__zoom_increment


    def move(self, direction):
        """ Move the player in a direction. """
        players = self.game_services.get_entity_manager().query(Player)
        for player in players:
            thrusters = player.get_component(Thrusters)
            if thrusters is not None:
                thrusters.direction += direction

    def turn(self, direction):
        """ Turn the player in a direction. """
        players = self.game_services.get_entity_manager().query(Player)
        for player in players:
            thrusters = player.get_component(Thrusters)
            if thrusters is not None:
                thrusters.turn += direction

    def start_shooting(self, point):
        """ Start shooting at a given point. """
        self.__shooting = True
        players = self.game_services.get_entity_manager().query(Player)
        for player in players:
            at = DirectionProviderScreen(point, player, self.__view)
            turrets = player.get_component(Turrets)
            for turret_ent in turrets.turrets:
                turret = turret_ent.get_component(Turret)
                turret.shooting_at = at

    def stop_shooting(self):
        """ Stop shooting. """
        self.__shooting = False
        players = self.game_services.get_entity_manager().query(Player)
        for player in players:
            turrets = player.get_component(Turrets)
            for turret_ent in turrets.turrets:
                turret = turret_ent.get_component(Turret)
                turret.shooting_at = None

    def maintain_aim(self, point):
        """ Keep aiming at the given point. """
        if self.__shooting:
            self.start_shooting(point)