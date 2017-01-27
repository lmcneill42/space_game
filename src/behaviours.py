""" Object behaviours for the game and game objects composed out of them.

See utils.py for the overall scheme this fits into.

"""

from pymunk.vec2d import Vec2d
from utils import Component, Timer
from physics import Body, Physics, CollisionHandler, CollisionResult, Thruster

import pygame
import random
        
class FollowsTracked(Component):

    def update(self, dt):
        """ Follows the tracked body. """

        body = self.get_component(Body)
        player_body = self.get_component(Tracking).get_tracked()

        if body is None or player_body is None:
            return
        
        displacement = player_body.position - body.position
        rvel = player_body.velocity - body.velocity
        target_dist = self.config["desired_distance_to_player"]

        # distality is a mapping of distance onto the interval [0,1) to
        # interpolate between two behaviours
        distality = 1 - 2 ** ( - displacement.length / target_dist )
        direction = ( 1 - distality ) * rvel.normalized() + distality * displacement.normalized()

        # Determine the fraction of our thrust to apply. This is governed by
        # how far away the target is, and how far away we want to be.
        frac = min(max(displacement.length / target_dist, rvel.length/200), 1)

        # Apply force in the interpolated direction.
        thrust = body.mass * self.config["acceleration"]
        force = frac * thrust * direction
        body.force = force

class ShootingAt(object):
    """ An object that defines a direction in which to shoot. """
    def __init__(self):
        pass
    def direction(self):
        pass

class ShootingAtScreen(object):
    """ Shooting at a point in screen space. """
    def __init__(self, pos, body, camera):
        self.__pos = pos
        self.__camera = camera
        self.__body = body
    def direction(self):
        return (self.__camera.screen_to_world(self.__pos) - self.__body.position).normalized()

class ShootingAtWorld(object):
    """ Shooting at a point in world space. """
    def __init__(self, pos, body):
        self.__pos = pos
        self.__body = body
    def direction(self):
        return (self.__pos - self.__body.position).normalized()

class ShootingAtDirection(object):
    """ Shooting in a particular direction. """
    def __init__(self, direction):
        self.__direction = direction
    def direction(self):
        return self.__direction

class ShootingAtBody(object):
    """ Shooting at a body. """
    def __init__(self, from_body, to_body):
        self.__from_body = from_body
        self.__to_body = to_body
    def direction(self):
        return (-self.__to_body.position + self.__from_body.position).normalized()

class ManuallyShootsBullets(Component):
    """ Something that knows how to spray bullets. Note that this is not a
    game object, it's something game objects can use to share code. """

    def __init__(self, entity, game_services, config):
        """ Inject dependencies and set up default parameters. """
        Component.__init__(self, entity, game_services, config)
        self.shooting_at = None
        self.shot_timer = 0

    def start_shooting_dir(self, direction):
        self.shooting_at = ShootingAtDirection(direction)

    def start_shooting_world(self, at):
        """ Start shooting at a point in world space. """
        self.shooting_at = ShootingAtWorld(at, self.get_component(Body))

    def start_shooting_at_body(self, body):
        """ Start shooting at a body. """
        self.shooting_at = ShootingAtBody(body, self.get_component(Body))

    def start_shooting_screen(self, at):
        """ Start shooting at a point in screen space. """
        self.shooting_at = ShootingAtScreen(at, self.get_component(Body), self.game_services.get_camera())

    def stop_shooting(self):
        """ Stop spraying bullets. """
        self.shooting_at = None

    @property
    def shooting(self):
        return self.shooting_at is not None

    def update(self, dt):
        """ Create bullets if shooting. Our rate of fire is governed by a timer. """

        # Count down to shootin.
        if self.shot_timer > 0:
            self.shot_timer -= dt

        # If we're shooting, let's shoot some bullets!
        if self.shooting:

            # These will be the same for each shot, so get them here...
            body = self.get_component(Body)
            shooting_at_dir = self.shooting_at.direction()

            # If it's time, shoot a bullet and rest the timer. Note that
            # we can shoot more than one bullet in a time step if we have
            # a high enough rate of fire.
            while self.shot_timer <= 0:

                # Update the timer.
                self.shot_timer += 1.0/self.config["shots_per_second"]

                # Can't spawn bullets if there's nowhere to put them!
                if body is None:
                    continue

                # Position the bullet somewhere sensible.
                separation = body.size*2
                bullet_position = Vec2d(body.position) + shooting_at_dir * separation

                # Work out the muzzle velocity.
                muzzle_velocity = shooting_at_dir * self.config["bullet_speed"]
                spread = self.config["spread"]
                muzzle_velocity.rotate_degrees(random.random() * spread - spread)
                bullet_velocity = body.velocity+muzzle_velocity

                # Create the bullet.
                self.create_entity(self.config["bullet_config"],
                                        parent=self.entity,
                                        team=self.get_component(Team).get_team(),
                                        position=bullet_position,
                                        velocity=bullet_velocity)

class Tracking(Component):
    """ Tracks something on the opposite team. """

    # Note: Camera does a kind of tracking, but with an explicitly
    # specified object, not the closest object on the other team. If
    # the concept of multiple tracking behaviours were introduced, the
    # camera could use the Tracking component.

    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.__tracked_body = None

    def get_tracked(self):
        """ Get the tracked body. """
        if self.__tracked_body is not None:
            if self.__tracked_body.is_garbage():
                self.__tracked_body = None
        return self.__tracked_body

    def reset_tracking(self):
        """ Stop tracking the current body and find something else. """
        self.__tracked_body = None

    def towards_tracked(self):
        """ Get the direction towards the tracked body. """
        body = self.get_tracked()
        if body is None:
            return Vec2d(0, 1)
        return (body.position - self.get_component(Body).position).normalized()

    def update(self, dt):
        """ Update the tracking. """

        # Ensure the object we're tracking still exists.
        if self.__tracked_body is not None:
            if self.__tracked_body.is_garbage():
                self.__tracked_body = None

        # Update tracking.
        if self.__tracked_body is None:

            # Find the closest object we don't like.
            self_team = self.get_component(Team)
            def f(body):
                team = body.get_component(Team)
                if self_team is None:
                    return False
                if team is None:
                    return False
                return not team.on_same_team(self_team)
            closest = self.get_system_by_type(Physics).closest_body_with(
                self.get_component(Body).position,
                f
            )
            if closest:
                self.__tracked_body = closest

class AutomaticallyShootsBullets(Component):
    """ Something that shoots bullets at something else. """

    def __init__(self, entity, game_services, config):
        """ Initialise. """
        Component.__init__(self, entity, game_services, config)
        self.fire_timer = Timer(config["fire_period"])
        self.fire_timer.advance_to_fraction(0.8)
        self.burst_timer = Timer(config["burst_period"])

    def update(self, dt):
        """ Update the shooting bullet. """

        body = self.get_component(Body)
        gun = self.get_component(ManuallyShootsBullets)
        tracking = self.get_component(Tracking)
        tracked_body = tracking.get_tracked()

        # Not much we can do if no bodies...
        if body is None or tracked_body is None:
            return

        # Point at the object we're tracking. Note that in future it would be
        # good for this to be physically simulated, but for now we just hack
        # it in...
        direction = (tracked_body.position - body.position).normalized()
        body.orientation = 90 + direction.angle_degrees

        # Shoot at the object we're tracking.
        if not gun.shooting:
            if self.fire_timer.tick(dt):
                self.fire_timer.reset()
                gun.start_shooting_at_body(tracked_body)
        else:
            if self.burst_timer.tick(dt):
                self.burst_timer.reset()
                gun.stop_shooting()

class LaunchesFighters(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.spawn_timer = Timer(config["spawn_period"])
    def update(self, dt):
        if self.spawn_timer.tick(dt):
            self.spawn_timer.reset()
            self.spawn()
    def spawn(self):
        for i in xrange(self.config["num_fighters"]):
            direction = self.get_component(Tracking).towards_tracked()
            spread = self.config["takeoff_spread"]
            direction.rotate_degrees(spread*random.random()-spread/2.0)
            body = self.get_component(Body)
            child = self.create_entity(self.config["fighter_config"],
                                            team=self.get_component(Team).get_team(),
                                            position=body.position,
                                            velocity=body.velocity + direction * self.config["takeoff_speed"])

class KillOnTimer(Component):
    """ For objects that should be destroyed after a limited time. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.lifetime = Timer(config["lifetime"])
    def update(self, dt):
        if self.lifetime.tick(dt):
            self.entity.kill()

class ExplodesOnDeath(Component):
    """ For objects that spawn an explosion when they die. """
    def on_object_killed(self):
        body = self.get_component(Body)
        explosion = self.create_entity(self.config["explosion_config"],
                                            position=body.position,
                                            velocity=body.velocity)
        shake_factor = self.config.get_or_default("shake_factor", 1)
        self.game_services.get_camera().apply_shake(shake_factor, body.position)

class EndProgramOnDeath(Component):
    """ If the entity this is attached to is destroyed, the program will exit. """
    def on_object_killed(self):
        self.game_services.end_game()

class Hitpoints(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.hp = self.config["hp"]
        self.max_hp = self.config["hp"] # Rendundant, but code uses this.

    def receive_damage(self, amount):
        self.hp -= amount
        if self.hp <= 0:
            self.entity.kill()

class DamageOnContact(Component):
    def apply_damage(self, hitpoints):
        """ Apply damage to an object we've hit. """
        if self.config.get_or_default("destroy_on_hit", True):
            self.entity.kill()
        if hitpoints is not None:
            hitpoints.receive_damage(self.config["damage"])

class DamageCollisionHandler(CollisionHandler):
    """ Collision handler to apply bullet damage. """
    def __init__(self):
        CollisionHandler.__init__(self, DamageOnContact, Hitpoints)
    def handle_matching_collision(self, dmg, hp):
        if hp.entity.is_ancestor(dmg.entity):
            return CollisionResult(False, False)
        dmg.apply_damage(hp)
        return CollisionResult(True, True)

class Team(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.__team = config.get_or_none("team")
    def setup(self, **kwargs):
        if "team" in kwargs:
            self.__team = kwargs["team"]
    def get_team(self):
        return self.__team
    def set_team(self, team):
        self.__team = team
    def on_same_team(self, that):
        return self.__team == None or that.__team == None or self.__team == that.__team

class Text(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.text = config.get_or_default("text", "Hello, world!")
    def setup(self, **kwargs):
        Component.setup(self, **kwargs)
        if "text" in kwargs:
            self.text = kwargs["text"]

class Thrusters(Component):
    """ Thruster component. This allows an entity with a body to move itself.
    Eventually I intend to have the thrusters be configurable, but for now its
    hard coded."""

    def __init__(self, entity, game_services, config):
        """ Initialise - set up the enginges. """
        Component.__init__(self, entity, game_services, config)
        self.__direction = Vec2d(0, 0)
        self.__dir_right = Vec2d(1, 0)
        self.__dir_backwards = Vec2d(0, 1)
        self.__turn = 0

    def setup(self, **kwargs):
        Component.setup(self, **kwargs)

        # Note: this is hard coded for now, but in future we could specify the
        # thruster layout in the config.
        body = self.get_component(Body)
        body.add_thruster(Thruster(Vec2d(-20, -20), Vec2d( 1,  0), self.config["max_thrust"] / 8))
        body.add_thruster(Thruster(Vec2d(-20,  20), Vec2d( 1,  0), self.config["max_thrust"] / 8))
        body.add_thruster(Thruster(Vec2d( 20, -20), Vec2d(-1,  0), self.config["max_thrust"] / 8))
        body.add_thruster(Thruster(Vec2d( 20,  20), Vec2d(-1,  0), self.config["max_thrust"] / 8))
        body.add_thruster(Thruster(Vec2d(  0, -20), Vec2d( 0,  1), self.config["max_thrust"] / 4))
        body.add_thruster(Thruster(Vec2d(  0,  20), Vec2d( 0, -1), self.config["max_thrust"]    ))

    def go_forwards(self):
        self.__direction -= self.__dir_backwards

    def go_backwards(self):
        self.__direction += self.__dir_backwards

    def go_left(self):
        self.__direction -= self.__dir_right

    def go_right(self):
        self.__direction += self.__dir_right

    def set_direction(self, direction):
        self.__direction = Vec2d(direction)

    def turn_left(self):
        self.__turn += 1

    def turn_right(self):
        self.__turn -= 1

    def update(self, dt):
        """ Update the engines, and automatically counteract spin."""

        # Cant do much without a body.
        body = self.get_component(Body)
        if body is None:
            return

        # Automatically counteract spin.
        turn = self.__turn
        if turn == 0 and self.__direction.x == 0:
            eps = 10 # LOLOLOL
            if body.angular_velocity > eps:
                turn = -1
            elif body.angular_velocity < -eps:
                turn = 1

        # Fire the right thrusters on the body.
        body.fire_correct_thrusters(self.__direction, turn)

class WaveSpawner(Component):
    """ Spawns waves of enemies. """

    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.wave = 1
        self.spawned = []
        self.message = None
        self.done = False

    def update(self, dt):
        """ Update the spawner. """
        Component.update(self, dt)

        # Check for end condition and show game ending message if so.
        if self.done:
            return
        elif self.player_is_dead() or self.max_waves():
            self.done = True
            txt = "GAME OVER"
            if self.max_waves():
                txt = "VICTORY"
            message = self.create_entity("endgame_message.txt", text=txt)

        # If the wave is dead and we're not yet preparing (which displays a timed message) then
        # start preparing a wave.
        if self.wave_is_dead() and self.message is None:
            self.prepare_for_wave()

        # If we're prepared to spawn i.e. the wave is dead and the message has gone, spawn a wave!
        if self.prepared_to_spawn():
            self.spawn_wave()

    def player_is_dead(self):
        """ Check whether the player is dead. """
        player = self.game_services.get_player()
        return player.is_garbage

    def spawn_wave(self):
        """ Spawn a wave of enemies, each one harder than the last."""
        player = self.game_services.get_player()
        player_body = player.get_component(Body)
        self.wave += 1
        for i in xrange(self.wave-1):
            enemy_type = random.choice(("enemies/destroyer.txt",
                                        "enemies/carrier.txt"))
            rnd = random.random()
            x = 1 - rnd*2
            y = 1 - (1-rnd)*2
            enemy_position = player_body.position + Vec2d(x, y)*500
            self.spawned.append(self.create_entity(enemy_type,
                                                        position=enemy_position,
                                                        team="enemy"))

    def wave_is_dead(self):
        """ Has the last wave been wiped out? """
        self.spawned = filter(lambda x: not x.is_garbage, self.spawned)
        return len(self.spawned) == 0

    def prepare_for_wave(self):
        """ Prepare for a wave. """
        self.message = self.create_entity("update_message.txt",
                                               text="WAVE %s PREPARING" % self.wave)

    def prepared_to_spawn(self):
        """ Check whether the wave is ready. """
        if self.message is None or not self.wave_is_dead():
            return False
        if self.message.is_garbage:
            self.message = None
            return True
        return False

    def max_waves(self):
        """ Check whether the player has beaten enough waves. """
        return self.wave == 10

class HardPoint(object):
    """ A slot that can contain a weapon. """

    def __init__(self, position):
        """ Initialise the hardpoint. """
        self.__position = position
        self.__weapon = None

    def set_weapon(self, weapon_entity, body_to_add_to):
        """ Set the weapon, freeing any existing weapon. """

        # If there is already a weapon then we need to delete it.
        if self.__weapon is not None:
            self.__weapon.kill()

        # Ok, set the new weapon.
        self.__weapon = weapon_entity

        # If the weapon has been unset, then our work is done.
        if self.__weapon is None:
            return

        # If a new weapon has been added then pin it to our body.
        weapon_body = self.__weapon.get_component(Body)
        point = body_to_add_to.local_to_world(self.__position)
        weapon_body.position = point
        weapon_body.velocity = body_to_add_to.velocity
        weapon_body.pin_to(body_to_add_to)

class Turrets(Component):

    def __init__(self, entity, game_services, config):
        """ Initialise the turrets. """
        Component.__init__(self, entity, game_services, config)
        self.__hardpoints = []
        hardpoints = config.get_or_default("hardpoints", [])
        for hp in hardpoints:
            if not "x" in hp or not "y" in hp:
                continue
            self.__hardpoints.append(HardPoint(Vec2d(hp["x"], hp["y"])))
            weapon_config = "enemies/turret.txt"
            if "weapon_config" in hp:
                weapon_config = hp["weapon_config"]
            self.set_weapon(len(self.__hardpoints)-1, weapon_config)

    def num_hardpoints(self):
        """ Get the number of hardpoints. """
        return len(self.__hardpoints)

    def set_weapon(self, hardpoint_index, weapon_config_name):
        """ Set the weapon on a hardpoint. Note that the weapon is an actual
        entity, which is set up as a child of the entity this component is
        attached to. It is assumed to have a Body component, which is pinned
        to our own Body."""
        entity = self.create_entity(weapon_config_name,
                                         parent=self.entity,
                                         team=self.get_component(Team).get_team())
        self.__hardpoints[hardpoint_index].set_weapon(entity, self.get_component(Body))

class Camera(Component):
    """ A camera, which drawing is done in relation to. """

    def __init__(self, entity, game_services, config):
        """ Initialise the camera. """
        Component.__init__(self, entity, game_services, config)
        self.__position = Vec2d(0, 0)
        self.__screen = game_services.get_screen()
        self.__max_shake = 20
        self.__damping_factor = 10
        self.__shake = 0
        self.__vertical_shake = 0
        self.__horizontal_shake = 0
        self.__tracking = None
        self.__zoom = 1

    def track(self, entity):
        """ Make the camera follow a particular game object. """
        self.__tracking = entity

    def surface(self):
        """ Get the surface drawing will be done on. """
        return self.__screen

    def world_to_screen(self, world):
        """ Convert from world coordinates to screen coordinates. """
        centre = Vec2d(self.__screen.get_size())/2
        return self.__zoom * (world - self.position) + centre

    def screen_to_world(self, screen):
        """ Convert from screen coordinates to world coordinates. """
        centre = Vec2d(self.__screen.get_size())/2
        return (screen - centre) / self.__zoom + self.position

    def check_bounds_world(self, bbox):
        """ Check whether a world space bounding box is on the screen. """
        if bbox is None: return True
        self_box = self.__screen.get_rect()
        self_box.width /= self.__zoom
        self_box.height /= self.__zoom
        self_box.center = self.position
        return bbox.colliderect(self_box)

    def check_bounds_screen(self, bbox):
        """ Check whether a screen space bounding box is on the screen. """
        if bbox is None: return True
        return self.__screen.get_rect().colliderect(bbox)

    def update(self, dt):
        """ Update the camera. """

        # If the object we're tracking has been killed then forget about it.
        if self.__tracking.is_garbage:
            self.__tracking = None

        # Move the camera to track the body. Note that we could do something
        # more complex e.g. interpolate the positions, but this is good enough
        # for now.
        tracked_body = self.__tracking.get_component(Body)
        if tracked_body is not None:
            self.__position = tracked_body.position

        # Calculate the screen shake effect.
        if self.__shake > 0:
            self.__shake -= dt * self.__damping_factor
        if self.__shake < 0:
            self.__shake = 0
        self.__vertical_shake = (1-2*random.random()) * self.__shake
        self.__horizontal_shake = (1-2*random.random()) * self.__shake

    def apply_shake(self, shake_factor, position):
        """ Apply a screen shake effect. """
        displacement = self.__position - position
        distance = displacement.length
        screen_diagonal = (Vec2d(self.__screen.get_size())/2).length
        max_dist = screen_diagonal * 2
        amount = max(shake_factor * (1.0 - distance/max_dist), 0)
        self.__shake = min(self.__shake+amount, self.__max_shake)

    @property
    def position(self):
        """ Get the position of the camera, adjusted for shake. """
        return self.__position + Vec2d(self.__horizontal_shake,
                                       self.__vertical_shake)

    @position.setter
    def position(self, value):
        """ Set the (actual) position of the camera. """
        self.__position = Vec2d(value)

    @property
    def zoom(self):
        """ Get the zoom level. """
        return self.__zoom

    @zoom.setter
    def zoom(self, value):
        """ Set the zoom level. """
        if value > 0:
            self.__zoom = value
