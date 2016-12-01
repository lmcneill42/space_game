""" Object behaviours for the game and game objects composed out of them.

See utils.py for the overall scheme this fits into.

"""

from vector2d import Vec2d
from utils import Component, Timer
from physics import Body, Physics, CollisionHandler, CollisionResult

import pygame
import random
        
class EnemyBehaviour(Component):
    def towards_player(self):
        """ Get the direction towards the player. """
        player = self.game_services.get_player()
        if player.is_garbage:
            return Vec2d(0, 1)
        player_pos = player.get_component(Body).position
        displacement = player_pos - self.get_component(Body).position
        direction = displacement.normalized()
        return direction

class FollowsPlayer(EnemyBehaviour):
    def __init__(self, game_object, game_services, config):
        EnemyBehaviour.__init__(self, game_object, game_services, config)

    def update(self, dt):

        # accelerate towards the player and tries to match velocities when close
        player = self.game_services.get_player()
        if player.is_garbage:
            return
        
        body = self.get_component(Body)
        player_body = player.get_component(Body)
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
        return (self.__to_body.position - self.__from_body.position).normalized()

class ManuallyShootsBullets(Component):
    """ Something that knows how to spray bullets. Note that this is not a
    game object, it's something game objects can use to share code. """

    def __init__(self, game_object, game_services, config):
        """ Inject dependencies and set up default parameters. """
        Component.__init__(self, game_object, game_services, config)
        self.shooting_at = None
        self.shot_timer = 0

    def start_shooting_dir(self, direction):
        self.shooting_at = ShootingAtDirection(direction)

    def start_shooting_world(self, at):
        """ Start shooting at a point in world space. """
        self.shooting_at = ShootingAtWorld(at, self.get_component(Body))

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
        if self.shot_timer > 0:
            self.shot_timer -= dt
        if self.shooting:
            body = self.get_component(Body)
            shooting_at_dir = self.shooting_at.direction()
            while self.shot_timer <= 0:
                self.shot_timer += 1.0/self.config["shots_per_second"]
                bullet = self.create_game_object(self.config["bullet_config"], parent=self.game_object)
                muzzle_velocity = shooting_at_dir * self.config["bullet_speed"]
                spread = self.config["spread"]
                muzzle_velocity.rotate(random.random() * spread - spread)
                bullet_body = bullet.get_component(Body)
                bullet_body.velocity = body.velocity + muzzle_velocity
                separation = body.size+bullet_body.size+1
                bullet_body.position = Vec2d(body.position) + shooting_at_dir * separation

class AutomaticallyShootsBullets(Component):
    """ Something that shoots bullets at something else. """

    def __init__(self, game_object, game_services, config):
        """ Initialise. """
        Component.__init__(self, game_object, game_services, config)
        self.fire_timer = Timer(config["fire_period"])
        self.fire_timer.advance_to_fraction(0.8)
        self.burst_timer = Timer(config["burst_period"])
        self.tracking = None

    def update(self, dt):
        """ Update the shooting bullet. """

        body = self.get_component(Body)
        gun = self.get_component(ManuallyShootsBullets)

        # Update tracking.
        if not self.tracking:

            # Find the closest object we don't like.
            self_team = self.get_component(Team)
            def f(body):
                if self_team is None:
                    return True
                team = body.get_component(Team)
                if team is not None:
                    return team.team() != self_team.team()
                return True
            closest = self.get_system_by_type(Physics).closest_body_with(
                body.position,
                f
            )
            if closest:
                self.tracking = closest

        # Update aim.
        if self.tracking:
            if self.tracking.is_garbage():
                self.tracking = None
        if self.tracking:
            if not gun.shooting:
                if self.fire_timer.tick(dt):
                    self.fire_timer.reset()
                    gun.start_shooting_world(self.tracking.position)
            else:
                if self.burst_timer.tick(dt):
                    self.burst_timer.reset()
                    gun.stop_shooting()
                else:
                    # Maintain aim.
                    gun.start_shooting_world(self.tracking.position)

class MovesCamera(Component):
    def update(self, dt):
        self.game_services.get_camera().position = Vec2d(self.get_component(Body).position)

class LaunchesFighters(EnemyBehaviour):
    def __init__(self, game_object, game_services, config):
        Component.__init__(self, game_object, game_services, config)
        self.spawn_timer = Timer(config["spawn_period"])
    def update(self, dt):
        if self.spawn_timer.tick(dt):
            self.spawn_timer.reset()
            self.spawn()
    def spawn(self):
        for i in xrange(self.config["num_fighters"]):
            direction = self.towards_player()
            spread = self.config["takeoff_spread"]
            direction.rotate(spread*random.random()-spread/2.0)
            child = self.create_game_object(self.config["fighter_config"])
            body = self.get_component(Body)
            child_body = child.get_component(Body)
            child_body.velocity = body.velocity + direction * self.config["takeoff_speed"]
            child_body.position = Vec2d(body.position)

class KillOnTimer(Component):
    """ For objects that should be destroyed after a limited time. """
    def __init__(self, game_object, game_services, config):
        Component.__init__(self, game_object, game_services, config)
        self.lifetime = Timer(config["lifetime"])
    def update(self, dt):
        if self.lifetime.tick(dt):
            self.game_object.kill()

class ExplodesOnDeath(Component):
    """ For objects that spawn an explosion when they die. """
    def on_object_killed(self):
        body = self.get_component(Body)
        position = body.position
        explosion = self.create_game_object(self.config["explosion_config"])
        explosion.get_component(Body).position = position
        shake_factor = self.config.get_or_default("shake_factor", 1)
        self.game_services.get_camera().apply_shake(shake_factor, position)

class EndProgramOnDeath(Component):
    """ If the entity this is attached to is destroyed, the program will exit. """
    def on_object_killed(self):
        self.game_services.end_game()

class Hitpoints(Component):
    def __init__(self, game_object, game_services, config):
        Component.__init__(self, game_object, game_services, config)
        self.hp = self.config["hp"]
        self.max_hp = self.config["hp"] # Rendundant, but code uses this.

    def receive_damage(self, amount):
        self.hp -= amount
        if self.hp <= 0:
            self.game_object.kill()

class DamageOnContact(Component):
    def apply_damage(self, hitpoints):
        """ Apply damage to an object we've hit. """
        if self.config.get_or_default("destroy_on_hit", True):
            self.game_object.kill()
        if hitpoints is not None:
            hitpoints.receive_damage(self.config["damage"])

class DamageCollisionHandler(CollisionHandler):
    """ Collision handler to apply bullet damage. """
    def __init__(self):
        CollisionHandler.__init__(self, DamageOnContact, Hitpoints)
    def handle_matching_collision(self, dmg, hp):
        if hp.game_object.is_ancestor(dmg.game_object):
            return CollisionResult(False, False)
        dmg.apply_damage(hp)
        return CollisionResult(True, True)

class Team(Component):
    def __init__(self, game_object, game_services, config):
        Component.__init__(self, game_object, game_services, config)
    def team(self):
        return self.config["team"]

class Text(Component):
    def __init__(self, game_object, game_services, config):
        Component.__init__(self, game_object, game_services, config)
        self.text = "Hello, world!"

class Thruster(object):
    def __init__(self, position, direction, max_thrust, name):
        self.__position = position
        self.__direction = direction
        self.__max_thrust = max_thrust
        self.__thrust = 0
        self.__name = name
    def go(self):
        self.__thrust = self.__max_thrust
    def stop(self):
        self.__thrust = 0
    def apply(self, body):
        if self.__thrust > 0:
            force = self.__direction * self.__thrust
            body.apply_force_at_local_point(force, self.__position)
    def world_position(self, body):
        return body.local_to_world(self.__position)
    def world_direction(self, body):
        return body.local_dir_to_world(self.__direction)
    def thrust(self):
        return self.__thrust
    def max_thrust(self):
        return self.__max_thrust
    def name(self):
        return self.name
    def on(self):
        return self.__thrust > 0

class Thrusters(Component):
    """ Thruster component. This allows an entity with a body to move itself.
    Eventually I intend to have the thrusters be configurable, but for now its
    hard coded."""

    def __init__(self, game_object, game_services, config):
        """ Initialise - set up the enginges. """
        Component.__init__(self, game_object, game_services, config)
        self.__top_left_thruster = \
            Thruster(Vec2d(-20, -20), Vec2d( 1,  0), config["max_thrust"] / 8, "top_left")
        self.__bottom_left_thruster = \
            Thruster(Vec2d(-20,  20), Vec2d( 1,  0), config["max_thrust"] / 8, "bottom_left")
        self.__top_right_thruster = \
            Thruster(Vec2d( 20, -20), Vec2d(-1,  0), config["max_thrust"] / 8, "top_right")
        self.__bottom_right_thruster = \
            Thruster(Vec2d( 20,  20), Vec2d(-1,  0), config["max_thrust"] / 8, "bottom_right")
        self.__top_thruster = \
            Thruster(Vec2d(  0, -20), Vec2d( 0,  1), config["max_thrust"] / 4, "top")
        self.__bottom_thruster = \
            Thruster(Vec2d(  0,  20), Vec2d( 0, -1), config["max_thrust"]    , "bottom")
        self.__thrusters = [self.__top_left_thruster, self.__top_right_thruster,
                            self.__top_thruster, self.__bottom_thruster,
                            self.__bottom_left_thruster, self.__bottom_right_thruster]
        self.__direction = Vec2d(0, 0)
        self.__dir_right = Vec2d(1, 0)
        self.__dir_backwards = Vec2d(0, 1)
        self.__turn = 0

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

    def stop_all_thrusters(self):
        """ Stop all the engines. """
        for thruster in self.__thrusters:
            thruster.stop()

    def fire_correct_thrusters(self, body):
        """ Perform logic to determine what engines are firing based on the
        desired direction. Automatically counteract spin. """

        # By default the engines should be of.
        self.stop_all_thrusters()

        # X
        if self.__direction.x > 0:
            self.__top_left_thruster.go()
            self.__bottom_left_thruster.go()
        elif self.__direction.x < 0:
            self.__top_right_thruster.go()
            self.__bottom_right_thruster.go()

        #Y
        if self.__direction.y > 0:
            self.__top_thruster.go()
        elif self.__direction.y < 0:
            self.__bottom_thruster.go()

        # turning thrusters
        if self.__turn > 0:
            self.__top_right_thruster.go()
            self.__bottom_left_thruster.go()
        elif self.__turn < 0:
            self.__top_left_thruster.go()
            self.__bottom_right_thruster.go()

        # Counteract spin automatically.
        eps = 0.005 # LOLOLOL
        if (not self.__top_left_thruster.on()) and \
           (not self.__top_right_thruster.on()) and \
           (not self.__bottom_left_thruster.on()) and \
           (not self.__bottom_right_thruster.on()): 
            if body.angular_velocity > eps:
                self.__top_right_thruster.go()
                self.__bottom_left_thruster.go()
            elif body.angular_velocity < -eps:
                self.__top_left_thruster.go()
                self.__bottom_right_thruster.go()

    def update(self, dt):
        """ Override update to switch on right engines and apply their effect."""

        # Cant do much without a body.
        body = self.get_component(Body)
        if body is None:
            return

        # Switch the right engines on.
        self.fire_correct_thrusters(body)

        # Apply physical effect of thrusters.
        for t in self.__thrusters:
            t.apply(body)

    def thrusters(self):
        """ Get the engines - useful for e.g. drawing. """
        return self.__thrusters

class WaveSpawner(Component):
    """ Spawns waves of enemies. """

    def __init__(self, game_object, game_services, config):
        Component.__init__(self, game_object, game_services, config)
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
            message = self.create_game_object("endgame_message.txt")
            message_text = message.get_component(Text)
            if self.max_waves():
                message_text.text = "VICTORY"
            else:
                message_text.text = "GAME OVER"

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
            enemy = self.create_game_object(enemy_type)
            rnd = random.random()
            x = 1 - rnd*2
            y = 1 - (1-rnd)*2
            enemy.get_component(Body).position = player_body.position + Vec2d(x, y)*500
            self.spawned.append(enemy)

    def wave_is_dead(self):
        """ Has the last wave been wiped out? """
        self.spawned = filter(lambda x: not x.is_garbage, self.spawned)
        return len(self.spawned) == 0

    def prepare_for_wave(self):
        """ Prepare for a wave. """
        from drawing import TextDrawable # nasty: avoid circular dependency.
        self.message = self.create_game_object("update_message.txt")
        self.message.get_component(Text).text = "WAVE %s PREPARING" % self.wave

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
        weapon_body.pin_to(body_to_add_to)

class Turrets(Component):

    def __init__(self, game_object, game_services, config):
        """ Initialise the turrets. """
        Component.__init__(self, game_object, game_services, config)
        self.__hardpoints = [HardPoint(Vec2d(70, 0)), HardPoint(Vec2d(-70, 0))]
        self.set_weapon(0, "enemies/turret.txt")
        self.set_weapon(1, "enemies/turret.txt")

    def num_hardpoints(self):
        """ Get the number of hardpoints. """
        return len(self.__hardpoints)

    def set_weapon(self, hardpoint_index, weapon_config_name):
        """ Set the weapon on a hardpoint. Note that the weapon is an actual
        entity, which is set up as a child of the entity this component is
        attached to. It is assumed to have a Body component, which is pinned
        to our own Body."""
        entity = self.create_game_object(weapon_config_name, parent=self.game_object)
        self.__hardpoints[hardpoint_index].set_weapon(entity, self.get_component(Body))
