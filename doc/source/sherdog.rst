:mod:`sherdog` --- Sherdog Web Scraping API
===========================================

.. module:: sherdog
   :synopsis: Web Scraping API for fetching objects from Sherdog.com
.. moduleauthor:: John O'Connor
.. sectionauthor:: John O'Connor

----------

Recipes
=======


.. code-block:: python

    ##
    # Find fighter rivalries
    from sherdog import Sherdog
    from collections import Counter
    from itertools import chain

    matt = Sherdog.search_fighters("matt hughes")[0]
    c = Counter(chain.from_iterable(f.fighters for f in matt.fights))
    del c[matt]
    print c.most_common()

    ##
    # Find favorite specific victory methods
    c = Counter(f.victory_method for f in matt.fights if f.winner == matt)
    print c.most_common()

    ##
    # Find favorite general victory methods
    c = Counter(f.victory_method.partition(' ')[0] for f in matt.fights if f.winner == matt)
    print c.most_common()


    ##
    # Number of fights finished in the first round
    first_round_wins = sum(1 for f in matt.fights if f.round == 1)

    ##
    # Time spent in octagon (assuming 5 minute rounds)
    from datetime import timedelta
    octagon_time = lambda f: timedelta(minutes=5 * (f.round - 1)) + (f.time or timedelta(0))
    total_fight_time = sum((octagon_time(fight) for fight in matt.fights), timedelta(0))


High Level API
==============

.. class:: Sherdog

    The Sherdog class is a singleton which provides a simple API for reading data from Sherdog.com.

    Each class method returns an object which maps directly to entities from the website
    (:class:`Event`, :class:`Fighter`, :class:`Organization`). In theory,
    it is similar to an ORM but, in this case, the backend is a website.

    .. code-block:: python

       from sherdog import Sherdog

       tito = Sherdog.search_fighters('tito ortiz')[0]
       matt = Sherdog.search_fighters('matt hughes')[0]
       junior = Sherdog.search_fighters('junior dos santos')[0]

       fighters = (tito, matt, junior)

       # compare fighters by number of wins
       from operator import attrgetter
       key = attrgetter('wins')

       best = max(fighters, key=key)
       worst = min(fighters, key=key)
       print "%s has more wins than %s!" % (best, worst)

       rounds_fought = sum(f.round for f in matt.fights)
       print "Matt has fought a total of %d rounds" % rounds_fought


    .. classmethod:: get_fighter(id_or_url)

        Get a :class:`Fighter` object for the associated sherdog `id` or `url`.

        :param id_or_url: the sherdog `id` or `url` for a fighter.
        :type id_or_url: int or string
        :rtype: :class:`Fighter`

        See :class:`Fighter`.

    .. classmethod:: get_event(id_or_url)

        Get an :class:`Event` object for the associated sherdog `id` or `url`.

        :param id_or_url: the sherdog `id` or `url` for an event.
        :type id_or_url: int or string
        :rtype: :class:`Event`

        See :class:`Event`

    .. classmethod:: get_organization(id_or_url)

        Get an :class:`Organization` object using its `id` or `url`.

        :param id_or_url: the sherdog `id` or `url` for an organization.
        :type id_or_url: an integer or string
        :rtype: :class:`Organization`

        *Example:*

        Using the organization id:

        .. code-block:: python

           ufc = Sherdog.get_organization(2)

        Using a relative sherdog URL of the organization:

        .. code-block:: python

           ufc = Sherdog.get_organization('Ultimate-Fighting-Championship-2')

        See :class:`Organization`

    .. classmethod:: search_events(query)

        Search for events matching `query`.

        See :meth:`Event.search`

        *Example:*

        .. code-block:: python

           results = Sherdog.search_events('ufc 153')
           ufc153 = results[0]

    .. classmethod:: search_organizations(query)

        Search for organizations matching `query`.

        See :meth:`Organization.search`

        *Example:*

        .. code-block:: python

           results = Sherdog.search_organizations('ultimate fighting championship')
           ufc = results[0]

    .. classmethod:: search_fighters(query)

        Search for fighters matching `query`.

        See :meth:`Fighter.search`

        *Example:*

        .. code-block:: python

           results = Sherdog.search_fighters('tito ortiz')
           tito = results[0]


.. exception:: ObjectDoesNotExist

   Base exception raised when a sherdog object is instantiated with an id or url that does not exist. In other words this is raised
   when sherdog.com returns an http status code 404 for the underlying http request.



Sherdog Entities
----------------

.. class:: Fight

    Represents one fight from an event.

    .. attribute:: event

       An :class:`Event` object representing the event where the fight was held.

    .. attribute:: fighters

       A :meth:`frozenset` containing two :class:`Fighter` objects for the fighters involved.

    .. attribute:: victory_method

       A string representing the method of victory. Ex: "TKO (Punches)"

    .. attribute:: referee

       The name of the referee overseeing the fight. Ex: "Herb Dean"

    .. attribute:: round

       The round number when the fight ended.

    .. attribute:: time

       A python :class:`timedelta` object representing the minutes and seconds into the round when the fight ended.

    .. attribute:: winner

       A :class:`Fighter` object representing the winner of the fight.


.. class:: Fighter(id_or_url, \*\*kwargs)

    Represents a mixed martial arts fighter such as Tito Ortiz.

    .. classmethod:: search(query)

        Search for fighters matching the string `query`.

        :param query: name of fighter to search for
        :type query: string
        :rtype: list of :class:`Fighter` objects.


        *Example:*

        .. code-block:: python

           results = Fighter.search('tito ortiz')
           tito = results[0]

    .. method:: fights_in_common(other_fighter)

        Get a list of fights that two fighters have in common.

        :param other_fighter: fighter to compare
        :type other_fighter: a :class:`Fighter` object
        :rtype: a :class:`list` of :class:`Fight` objects.


        *Example:*

        .. code-block:: python

          matt_hughes = Sherdog.search_fighters("matt hughes")[0]
          bj_penn = Sherdog.search_fighters("bj penn")[0]
          rivalry = matt_hughes.fights_in_common(bj_penn)

    .. attribute:: name

       A string for the name of the fighter (ie. "Tito Ortiz")

    .. attribute:: nickname

       A string for the fighter's nickname. (ie. "Huntington Beach Badboy")

    .. attribute:: image_url

       A string with a URL to a thumbnail image for the fighter.

    .. attribute:: birthday

       A python :class:`date` object representing the date the fighter was born.

    .. attribute:: city

       A string for the name of the city where the fighter resides.

    .. attribute:: country

       A string for the name of the country where the fighter resides.

    .. attribute:: country_flag_url

       A string holding the URL to an image of the fighter's country flag.

    .. attribute:: height

       A string with the height of the fighter. (ie. 6'3")

    .. attribute:: weight

       A string with the weight of the fighter (ie. 100lbs)

    .. attribute:: weight_class

       A string with the name of the fighters weight class.

    .. attribute:: wins

       Number of fights won.

    .. attribute:: losses

       Number of fights lost.

    .. attribute:: fights

       List of :class:`Fight` objects that the fighter has fought in.

    .. exception:: DoesNotExist

       Raised when a :class:`Fighter` object is instantiated with an id or url that does not exist. In other words, raised
       when sherdog.com returns an http status code 404 for the underlying http request.


.. class:: Event(id_or_url, \*\*kwargs)

    Represents an event such as "UFC 153". An event is hosted by an organization
    at a venue and consists of one or more fights.

    .. classmethod:: search(query)

        Search for events with name matching `query`.

        :param query: name of event to search for
        :type query: string
        :rtype: list of :class:`Event` objects.

    .. attribute:: name

        A string representing the name of the event.

    .. attribute:: date

        A python :class:`date` object for the date of the event.

    .. attribute:: location

        A string representing the location of where the event was held. Includes city,
        state and country or any combination.

        Example: "Las Vegas, Nevada, United States".

    .. attribute:: location_thumb_url

        A string for the URL which refers to the thumbnail image of the country flag
        of the :attr:`location`.

    .. attribute:: venue

        A string representing the name of the venue where the event was held.

    .. attribute:: organization

        An :class:`Organization` object representing the organization hosting the event.

    .. attribute:: fights

        A list of :class:`Fight` objects representing the fights from the event.

    .. attribute:: url

       A relative url on sherdog.com which corresponds with the object.

       Example: "/events/BKF-2-Brazilian-King-Fighter-2-25419"

    .. attribute:: full_url

       The full url on sherdog.com which corresponds with the object.

       Example: "http://www.sherdog.com/events/BKF-2-Brazilian-King-Fighter-2-25419"

    .. exception:: DoesNotExist

       Raised when a :class:`Event` object is instantiated with an id or url that does not exist. In other words, raised
       when sherdog.com returns an http status code 404 for the underlying http request.


.. class:: Organization(id_or_url, \*\*kwargs)

   Represents an organization such as the Ultimate Fighting Championship.

   .. classmethod:: search(query)

      Search for organizations with name matching `query`.

      :param query: The organization name to search for
      :type query: string
      :rtype: List of :class:`Organization` objects.

   .. attribute:: name

      A string for the official name of the organization.

   .. attribute:: description

      A string describing the organization.

   .. attribute:: events

       A list of :class:`Event` objects hosted by the organization.

   .. exception:: DoesNotExist

       Raised when a :class:`Organization` object is instantiated with an id or url that does not exist. In other words, raised
       when sherdog.com returns an http status code 404 for the underlying http request.

