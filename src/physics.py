from .utils import *

import pymunk
import math

import numpy
import scipy.optimize

class Physics(ComponentSystem):
    """ Physics system. It's now implemented using pymunk, but that fact should
        not leak out of this file! Entitys that need to be simulated should
        be given Body components which will be managed by a Physics system. """

    def __init__(self):
        """ Initialise physics. """
        ComponentSystem.__init__(self)
        
        # List of collision handlers. These operate in terms of types of
        # entity. We implement them using a pymunk collision handler.
        self.collision_handlers = []

        # The pymunk space.
        self.space = pymunk.Space()

        # Note: the this function assumes we have snuck a reference to our
        # own body into the pymunk shape. Which we have: see Body(). Here
        # we try each handler in turn till we find one that is compatible.
        def collide_begin(arbiter, space, data):
            go1 = arbiter.shapes[0].game_body.entity
            go2 = arbiter.shapes[1].game_body.entity
            for handler in self.collision_handlers:
                result = handler.handle_collision(go1, go2)
                if result.handled:
                    return result.wants_physical_simulation
            return True

        # Setup our simple pymunk collision handler.
        self.pymunk_handler = self.space.add_collision_handler(1, 1)
        self.pymunk_handler.begin = lambda a, s, d: collide_begin(a, s, d)

        # Setup a default handler for non-collideable objects.
        self.default_handler = self.space.add_default_collision_handler()
        self.default_handler.begin = lambda a, s, d: False

    def create_queued_component(self, body):
        """ Add a body to the simulation, initialising it. """
        body.create(self.space)
        ComponentSystem.create_queued_component(self, body)

    def add_body(self, body):
        """ As above. """
        self.add_component(self, body)

    def remove_component(self, body):
        """ Remove a body from the simulation, deinitialising it. """
        ComponentSystem.remove_component(self, body)
        body.destroy()

    def remove_body(self, body):
        """ As above. """
        self.remove_component(self, body)

    def add_collision_handler(self, handler):
        """ Add a logical collision handler for the game. """
        self.collision_handlers.append(handler)

    def update(self, dt):
        """ Advance the simulation. """
        ComponentSystem.update(self, dt)
        self.space.step(dt)

    def closest_body_with(self, point, f):
        """ Find the closest body of a given predicate. """
        bodies = filter(f, self.components)
        best_yet = None
        best_length_yet = None
        for b in bodies:
            length = (b.position - point).length
            if not best_yet or length < best_length_yet:
                best_yet = b
                best_length_yet = length
        return best_yet

    def get_entity_at(self, point):
        """ Get the entity at a point. """
        pqs = self.space.point_query(point, 5, pymunk.ShapeFilter())
        for pq in pqs:
            if pq.shape is not None:
                body = pq.shape.game_body
                return body.entity
        return None


class Body(Component):
    """ Physical body attached to a entity. Note that it's implemented
    in terms of pymunk now. It will need to change since we're currently
    using pymunk in a pretty horrendous way: this was to preserve the original
    interface while integrating pymunk. But we should stop mucking around with
    position / velocity / size (!) and use forces instead. """
    
    def __init__(self, entity, game_services, config):
        """ Initialise the body, attached to the given entity. """

        Component.__init__(self, entity, game_services, config)

        # Moment of inertia.
        moment = pymunk.moment_for_circle(float(config.get_or_default("mass", 1)),
                                          0,
                                          config.get_or_default("size", 5))

        # Initialise body and shape.
        self.__body = pymunk.Body(float(config.get_or_default("mass", 1)), moment)
        self.__shape = pymunk.Circle(self.__body, float(config.get_or_default("size", 5)))
        self.__shape.friction = 0.8

        # Collision type for non-collidable bodies.
        if config.get_or_default("is_collideable", True):
            self.__shape.collision_type = 1
        else:
            self.__shape.collision_type = 0

        # Squirell ourself away inside the shape, so we can map back later. Note
        # that we're modifying the shape with a new field on the fly here, which
        # could be seen as a bit hacky, but I think it's fairly legit - it's just
        # as if we were to derive from pymunk.Shape and extend it, just without all
        # the code...
        self.__shape.game_body = self

        # We will need the space eventually.
        self.__space = None

        # Remember joints
        self.__joints = []

        # A body can have thrusters attached to it.
        self.__thrusters = []
        self.__thruster_configurations = {}

    def setup(self, **kwargs):
        """ Allow an initial position to be specified. """
        if "position" in kwargs:
            self.position = kwargs["position"]
        if "velocity" in kwargs:
            self.velocity = kwargs["velocity"]
            if self.velocity.length > 0:
                self.orientation = self.velocity.normalized().get_angle_degrees()+90
        if "orientation" in kwargs:
            self.orientation = kwargs["orientation"]

    def manager_type(self):
        return Physics

    def create(self, space):
        """ Actually add the body to the simulation. """
        if self.__space is None:
            self.__space = space
            self.__space.add(self.__body, self.__shape, *self.__joints)

    def destroy(self):
        """ Remove the body from the simulation. """
        if self.__space is not None:
            self.__space.remove(self.__body, self.__shape, *self.__joints)
            self.__space = None

    def world_to_local(self, point):
        return self.__body.world_to_local(point)

    def local_to_world(self, point):
        return self.__body.local_to_world(point)

    def local_dir_to_world(self, direction):
        return self.local_to_world(direction) - self.position

    def apply_force_at_local_point(self, force, point):
        """ Apply a force to the body."""
        self.__body.apply_force_at_local_point(force, point)

    def pin_to(self, body):
        """ Pin this body to that one. They will become inseparable, and will
        not collide with one another. They will be able to rotate relative to
        one another however. """

        # Setup the joint.
        joint = pymunk.constraint.PinJoint(
            self.__body,
            body.__body,
            (0, 0),
            body.world_to_local(self.position)
        )
        joint.collide_bodies = False

        # Remember the joint so it can be added and removed.
        self.__joints.append(joint)

        # If the body has already been created then add the joint to the simulation.
        if self.__space:
            self.__space.add(joint)

    def add_thruster(self, thruster):
        """ Add a thruster to the body. """
        self.__thrusters.append(thruster)

    def update(self, dt):
        """ Update the body. """
        Component.update(self, dt)
        # Apply physical effect of thrusters.
        for t in self.__thrusters:
            t.apply(self)

    def thrusters(self):
        """ Get the engines - useful for e.g. drawing. """
        return self.__thrusters

    def stop_all_thrusters(self):
        """ Stop all the engines. """
        for thruster in self.__thrusters:
            thruster.stop()

    def compute_correct_thrusters(self, direction, turn):
        """ Perform logic to determine what engines are firing based on the
        desired direction. Automatically counteract spin. We cope with an
        arbitrary configuration of thrusters through use of a mathematical
        optimisation algorithm (scipy.optimize.minimize.)

        Variables: t0, t1, t2, ...
        Function: g . f where
                  f(t0, t1, t2, ...) -> (acceleration, moment)
                  g(acceleration, moment) -> distance from desired (accel, moment)
        Constraint: t0min <= t0 <= t0max, ...

        Note: there may be a better way of solving this problem, I
        don't know. I will try to state the problem clearly here so
        that a better solution might present itself:

        Note: notation a little odd in the following:

        We have a set of N thrusters, (Tn, Dn, Pn, TMAXn), where "Tn" is
        the thruster's current (scalar) thrust, Pn is its position,
        and FMAXn is the maximum thrust it can exert. Dn is the direction
        of thrust, so the force currently being exerted, Fn, is Tn*Dn.

        The acceleration due to a given thruster:

            An = m * Fn

        where m is the mass of the body.

        The centre of mass is the origin O.

        The torque due to a given thruster is therefore

            Qn = |Pn| * norm(orth(Pn)) * Fn.

        The resultant force on the body, F', is F0+F1+...+Fn

        The resultant torque on the body, Q', is Q0+Q1+...+Qn

        The following constraints are in effect:

            T0 >= 0, T1 >= 0, ..., Tn >= 0

            T0 <= TMAX0, T1 <= TMAX1, Tn <= TMAXn

        In my implementation here, the vector T0..n is the input array for a
        function to be minimised.

        Note that this function is very slow. Some sort of caching scheme will be
        a must - and it would be good to share identical configurations between
        entities.

        I don't know whether there is an analytical solution to this problem.

        """

        def f(thrusts):
            """ Objective function. Determine the resultant force and torque on
            the body, and then apply heuristics (absolute guesswork!!) to determine
            the fitness. We can then use a minimisation algorithm to optimise the
            thruster configuration. """

            # Calculate the resultant force and moment from applying all thrusters.
            resultant_force = Vec2d(0, 0);
            resultant_moment = 0
            for i in range(0, len(thrusts)):
                thrust = float(thrusts[i])
                resultant_force += self.__thrusters[i].force_with_thrust(thrust)
                resultant_moment += self.__thrusters[i].moment_with_thrust(thrust)

            # We want to maximise the force in the direction in which we want to
            # be thrusting.
            force_objective = direction.normalized().dot(resultant_force)

            # We want to maximise the torque in the direction we want.
            moment_objective = numpy.sign(turn) * resultant_moment

            # We negate the values because we want to *minimise*
            return -force_objective -moment_objective
            
        # Initial array of values.
        thrusts = numpy.zeros(len(self.__thrusters))

        # Thrust bounds.
        thrust_bounds = [(0, thruster.max_thrust()) for thruster in self.__thrusters]

        # Optimise the thruster values.
        return scipy.optimize.minimize(f, thrusts, method="TNC", bounds=thrust_bounds)

    def fire_correct_thrusters(self, direction, torque):
        """ Perform logic to determine what engines are firing based on the
        desired direction. Automatically counteract spin. """

        # By default the engines should be of.
        self.stop_all_thrusters()

        # Come up with a dictionary key.
        key = (direction.x, direction.y, torque)

        # Ensure a configuration exists for this input.
        if not key in self.__thruster_configurations:
            self.__thruster_configurations[key] = \
                self.compute_correct_thrusters(direction, torque)

        # Get the cached configuration.
        result = self.__thruster_configurations[key]
        for i in range(0, len(result.x)):
            self.__thrusters[i].go(float(result.x[i]))

    def hit_scan(self, local_origin=Vec2d(0,0), local_direction=Vec2d(0,-1), distance=1000, radius=1):
        """ Do a hit scan computation. Return the bodies and hit locations of
        entities that intersect the line. Return: [(body, pos)]. """
        start = self.local_to_world(local_origin)
        end = self.local_to_world(local_direction*distance)
        results = self.__space.segment_query(start, end, radius, pymunk.ShapeFilter())
        for result in results:
            if not result.shape.game_body.entity.is_ancestor(self.entity):
                return (result.shape.game_body, result.point)
        return (None, end)
        
    @property
    def position(self):
        return self.__body.position

    @position.setter
    def position(self, value):
        self.__body.position = value

    @property
    def velocity(self):
        return self.__body.velocity

    @velocity.setter
    def velocity(self, value):
        self.__body.velocity = value

    @property
    def size(self):
        return self.__shape.radius

    @property
    def mass(self):
        return self.__body.mass

    @property
    def force(self):
        """ Note: force gets reset with each tick so no point caching it. """
        return self.__body.force

    @force.setter
    def force(self, value):
        """ Note: force gets reset with each tick so no point caching it. """
        self.__body.force = value

    @property
    def collideable(self):
        return self.__shape.collision_type == 1

    @collideable.setter
    def collideable(self, value):
        if value:
            self.__shape.collision_type = 1
        else:
            self.__shape.collision_type = 0

    @property
    def orientation(self):
        """ Note: Expose degrees because pygame likes degrees. """
        return math.degrees(self.__body.angle)

    @orientation.setter
    def orientation(self, value):
        """ Note: Expose degrees because pygame likes degrees. """
        self.__body.angle = math.radians(value)

    @property
    def angular_velocity(self):
        """ Note: Expose degrees because pygame likes degrees. """
        return math.degrees(self.__body.angular_velocity)

    @angular_velocity.setter
    def angular_velocity(self, value):
        """ Note: Expose degrees because pygame likes degrees. """
        self.__body.angular_velocity = math.radians(value)

class CollisionResult(object):
    def __init__(self, handled, wants_physical_simulation):
        self.handled = handled
        self.wants_physical_simulation = wants_physical_simulation

class CollisionHandler(object):
    """ A logical collision handler. While physical collision handling is
    dealt with by the physics implementation, game behaviours must be added
    by adding instances of this matching entity types. """
    
    def __init__(self, t1, t2):
        """ Initialise with a pair of types. """
        self.t1 = t1
        self.t2 = t2
        
    def handle_collision(self, o1, o2):
        """ Handle type colliding bodies if they have components of
        matching types. """
        c1 = o1.get_component(self.t1)
        c2 = o2.get_component(self.t2)
        c3 = o1.get_component(self.t2)
        c4 = o2.get_component(self.t1)
        # Note: behaviour undefined if both objects have both components. Need
        # to sort that out.
        if c1 is not None and c2 is not None:
            return self.handle_matching_collision(c1, c2)
        elif c3 is not None and c4 is not None:
            return self.handle_matching_collision(c4, c3)
        return CollisionResult(False, True)
    
    def handle_matching_collision(self, c1, c2):
        """ These components are colliding, so the game should do something. """
        return CollisionResult(False, True)

class Thruster(object):
    """ The logical definition of a thruster on a Body. """
    
    def __init__(self, position, direction, max_thrust):
        """ Initialise the thruster's parameters. """
        self.__position = position
        self.__direction = direction
        self.__max_thrust = max_thrust
        self.__thrust = 0

    def go(self, thrust=None):
        """ Set the thrust. """
        if thrust is None:
            thrust = self.__max_thrust
        self.__thrust = min(thrust, self.__max_thrust)

    def stop(self):
        """ Stop the thruster. """
        self.__thrust = 0

    def apply(self, body):
        """ Apply the thruster's force to a body. """
        if self.__thrust > 0:
            force = self.force_with_thrust(self.__thrust)
            body.apply_force_at_local_point(force, self.__position)

    def force_with_thrust(self, thrust):
        """ Given a thrust amount, get the force of the thruster in its
        direction of thrust. """
        return self.__direction * thrust

    def moment_with_thrust(self, thrust):
        """ Given a thrust amount, get the resulting torque. """
        # moment of force = r × F
        # where r is the distance vector from centre of mass to thruster,
        # F is the force vector and × denotes the cross product
        return self.__position.cross( self.force_with_thrust( thrust ) )

    def world_position(self, body):
        """ Get the world-space position of the thruster. """
        return body.local_to_world(self.__position)

    def world_direction(self, body):
        """ Get the world-space direction of thrust. """
        return body.local_dir_to_world(self.__direction)

    def thrust(self):
        """ Get the current scalar thrust amount. """
        return self.__thrust

    def max_thrust(self):
        """ Get the maximum scalar thrust amount. """
        return self.__max_thrust

    def on(self):
        """ Is the thruster firing? """
        return self.__thrust > 0
