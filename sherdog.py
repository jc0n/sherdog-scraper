"""
A simple API for scraping information about MMA fighters, fights, and events
from Sherdog.com
"""

__author__ = 'John O\'Connor'

import abc
import json
import math
import re
import urllib

from collections import namedtuple
from datetime import timedelta, datetime

# dependencies
import iso8601
from BeautifulSoup import BeautifulSoup

__all__ = ('Sherdog', 'Event', 'Fight', 'Fighter', 'Organization')

SHERDOG_URL = 'http://www.sherdog.com'

_EVENT_MATCH_RE = re.compile('module event_match')
_EVEN_ODD_RE = re.compile('^(even)|(odd)$')
_FIGHTER_LEFT_RE = re.compile('fighter left_side')
_FIGHTER_RIGHT_RE = re.compile('fighter right_side')
_FINAL_RESULT_RE = re.compile('^final_result')
_SUB_EVENT_RE = re.compile('subEvent')

_EVENTS_URL_RE = re.compile('^/events/')
_FIGHTER_URL_RE = re.compile('^/fighter/')

_SECONDS_IN_YEAR = 60 * 60 * 24 * 365

class LazySherdogObject(object):
    """
    Abstract base class for representing sherdog objects.

    All "sherdog" objects have an id associated with them which is used to
    instantiate a subclass of this abstract class. The properties of the object
    are populated lazily when they are required.
    """
    __metaclass__ = abc.ABCMeta
    _lazy = True

    # a string template for the objects' path on sherdog.com which one
    # argument for the numerical ID
    url_path_template = abc.abstractproperty()

    def __init__(self, id_or_url, **kwargs):
        """
        Abstract constructor

        Arguments:
            id_or_url: The numerical ID or web page url for the sherdog object

        Keyword Arguments:
            The keyword arguments dict is converted into properties on the object.
        """
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

        if isinstance(id_or_url, basestring):
            self.id = int(id_or_url[id_or_url.rfind('-') + 1:])
        else:
            self.id = int(id_or_url)

        self.url = self.url_path_template % self.id

    def __getattr__(self, key):
        if not self._lazy:
            raise AttributeError(key)

        self._lazy = False
        self._load_properties()
        return getattr(self, key)

    def __getitem__(self, key):
        return getattr(self, key)

    def __eq__(self, other):
        assert isinstance(other, LazySherdogObject)
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    @abc.abstractmethod
    def _load_properties(self):
        """
        Abstract method which is called the first time a property is accessed
        and does not exist. This method is only called once.
        """
        pass


class Organization(LazySherdogObject):
    """
    Represents an "Organization" such as the "Ultimate Fighting Championship".

    Attributes:
        name: The name of the organization.
        description: A brief string describing the organization.
        events: A list of `Event` objects for all events hosted by
                the organization.
    """
    url_path_template = '/organizations/X-%d'
    search_url_path_template = '/search/organizations/?q=%s'

    def _parse_basic_info(self, dom):
        name = dom.find('h2', {'itemprop': 'name'})
        if name is not None:
            self.name = name.text

        description = dom.find('div', {
            'class': 'data',
            'itemprop': 'description'
            })
        if description is not None:
            self.description = description.text

    def _parse_events(self, dom):
        table = dom.find('table', {'class': 'event'})
        rows = table.findAll('tr', {'class': _EVEN_ODD_RE})
        events = []
        for row in rows:
            datestr = row.find('meta', {'itemprop': 'startDate'})['content']
            date = iso8601.parse_date(datestr)
            name = row.find('span', {'itemprop': 'name'}).text
            location = row.find('td', {'itemprop': 'location'}).text
            event = Event(row.a['href'], date=date,
                          location=location, name=name)
            events.append(event)
        self.events = events

    def _load_properties(self):
        dom = Sherdog.fetch_and_parse_url(self.url)
        self._parse_basic_info(dom)
        self._parse_events(dom)

    @classmethod
    def search(cls, query):
        """
        Searches for organizations using an arbitrary string.

        Arguments:
            query: A string for the organization name to search.

        Returns:
            A list of `Organization` objects.
        """
        query = urllib.quote(query.lower())
        result = Sherdog.fetch_url(cls.search_url_path_template % query)
        data = json.loads(result)
        return [cls(orgdict['id'], **orgdict)
                    for orgdict in data['collection']]

    def __repr__(self):
        return repr(self.name)


class Fighter(LazySherdogObject):
    """
    Represents a fighter, such as "Junior Dos Santos".

    Attributes:
        age: number of years the fighter has been alive.
        birthday: date object representing fighter's birthday
        locality: string such as "Los Vegas, Nevada"
        country: string such as "United States"
        events: A list of `Event` objects in which the fighter has fought.
        full_url: The full url of the fighters profile on sherdog.com
        height: string such as 6'3"
        image_url: A URL for the fighter's profile image on sherdog.com
        losses: number of losses in the fighters career
        name: name of the fighter, ie. "Junior Dos Santos" or "Tito Ortiz"
        nickname: fighter's nickname, ie. "Cigano" or "The Huntington Beach Bad Boy"
        weight: string such as "260 lbs"
        weight_class: A string such as "Heavyweight"
        wins: number of wins in the fighters career
    """
    url_path_template = '/fighter/X-%d'
    search_url_path_template = '/stats/fightfinder?SearchTxt=%s'

    def __repr__(self):
        return repr(self.name)

    @property
    def age(self):
        seconds = (datetime.now() - self.birthday).total_seconds()
        return int(math.floor(seconds / _SECONDS_IN_YEAR))

    @property
    def full_url(self):
        return SHERDOG_URL + self.url

    @classmethod
    def search(cls, query):
        """
        Searches for fighters using an arbitrary string.

        Arguments:
            query: A string for the fighter name to be searched.

        Returns:
            A list of `Fighter` objects.
        """
        query = urllib.quote(query.lower())
        dom = Sherdog.fetch_and_parse_url(cls.search_url_path_template % query)
        table = dom.find('table', {'class': 'fightfinder_result'})
        urls = [a['href'] for a in table.findAll('a')]
        return map(cls, filter(_FIGHTER_URL_RE.match, urls))

    def _parse_basic_info(self, dom):
        image = dom.find('img', {
            'class': 'profile_image photo',
            'itemprop': 'image'
            })
        if image is not None:
            self.image_url = image['src']

        name = dom.find('span', {'class': 'fn'})
        if name is not None:
            self.name = name.text

        nickname = dom.find('span', {'class': 'nickname'})
        if nickname is not None:
            self.nickname = nickname.text.strip('\'"')

        birthday = dom.find('span', {'itemprop': 'birthDate'})
        if birthday is not None and '-' in birthday.text:
            self.birthday = datetime.strptime(birthday.text, "%Y-%m-%d").date()

    def _parse_location(self, dom):
        content = dom.find('span', {'class': 'item birthplace'})
        if content is None:
            return
        locality = content.find('span', {'class': 'locality'})
        if locality is not None:
            self.locality = locality.text

        country = content.find('strong', {'itemprop': 'nationality'})
        if country is not None:
            self.country = country.text
            self.country_flag_url = content.img['src'] if content.img else None

    def _parse_stats(self, dom):
        height = dom.find('span', {'class': 'item height'})
        if height is not None and hasattr(height, 'strong'):
            self.height = height.strong.text

        weight = dom.find('span', {'class': 'item weight'})
        if weight is not None and hasattr(height, 'strong'):
            self.weight = weight.strong.text

        wclass = dom.find('h6', {'class': 'item wclass'})
        if wclass is not None and hasattr(wclass, 'strong'):
            self.weight_class = wclass.strong.text

        win_graph = dom.find('div', {'class': 'bio_graph'})
        if win_graph is not None:
            counter = win_graph.find('span', {'class': 'counter'})
            self.wins = int(counter.text) if counter else 0

        lose_graph = dom.find('div', {'class': 'bio_graph loser'})
        if lose_graph is not None:
            counter = lose_graph.find('span', {'class': 'counter'})
            self.losses = int(counter.text) if counter else 0

    def _parse_events(self, dom):
        content = dom.find('div', {'class': 'content table'})
        if content and hasattr(content, 'table'):
            event_links = content.table.findAll('a', {'href': _EVENTS_URL_RE})
            self.events = [Event(a['href']) for a in event_links]

    def _load_properties(self):
        dom = Sherdog.fetch_and_parse_url(self.url)
        self._parse_basic_info(dom)
        self._parse_location(dom)
        self._parse_stats(dom)
        self._parse_events(dom)


class Fight(namedtuple('Fight', ('event', 'fighters', 'match',
                                 'method', 'referee', 'round',
                                 'time', 'winner'))):
    """
    Represents one fight from an event which may have multiple fights. If the
    fight has already happened the object will contain the results.

    Attributes:
        event: The `Event` object in which the fight took place.
        fighters: A 2-tuple of the `Fighter` objects for the fighters invovled.
        match: The number of the match as it occured in the event.
        method: The method of victory ie. "TKO (Punches)"
        referee: The referee of the fight ie. "Herb Dean"
        round: The round number in which the fight was won.
        time: The total time of the fight.
        winner: A `Fighter` object representing the winning fighter.
    """

    def __repr__(self):
        return u' vs. '.join([f.name.split(None, 1)[-1].title()
                                for f in self.fighters])


class Event(LazySherdogObject):
    """
    Represents an event consisting of one or more fights.

    Attributes:
        date: The date the event took place.
        fights: A list of `Fight` objects for the event's bouts.
        full_url: The full URL for the event profile on sherdog.com
        location: The location of the event.
        location_thumb_url: A URL for the country flag where the event occurred.
        name: The name of the event ie. "UFC 146 - Dos Santos vs. Mir"
        organization: An `Organization` object
        venue: The venue of the event ie. "MGM Grand Garden Arena"
    """

    url_path_template = '/events/X-%d'
    search_url_path_template = '/stats/fightfinder?SearchTxt=%s'

    @property
    def full_url(self):
        return SHERDOG_URL + self.url

    def __repr__(self):
        return repr(self.name)

    def _parse_fight_time(self, timestr):
        if not timestr or ':' not in timestr:
            return None
        minutes, seconds = timestr.split(':', 1)
        return timedelta(minutes=int(minutes), seconds=int(seconds))

    def _fight_winner(self, result, left, right):
        if result.text == u'draw':
            return None
        elif result.text == u'win':
            return left
        else:
            return right

    def _parse_main_fight(self, dom):
        left = dom.find('div', {'class': _FIGHTER_LEFT_RE}).h3.a
        left_fighter = Fighter(left['href'], name=left.text)

        right = dom.find('div', {'class': _FIGHTER_RIGHT_RE}).h3.a
        right_fighter = Fighter(right['href'], name=right.text)

        fighters = (left_fighter, right_fighter)
        result = dom.find('span', {'class': _FINAL_RESULT_RE})
        if result is None:
            return Fight(event=self, fighters=fighters,
                    winner=None, match=None, method=None, referee=None,
                    round=None, time=None)

        # parse match, method, ref, round, time
        td = dom.find('table', {'class':'resume'}).findAll('td')
        keys = [x.contents[0].text.lower() for x in td]
        values = [x.contents[-1].lstrip() for x in td]
        info = dict(zip(keys, values))
        time = self._parse_fight_time(info['time'])
        return Fight(event=self, fighters=fighters,
                winner=self._fight_winner(result, left_fighter, right_fighter),
                match=int(info['match']), method=info['method'],
                referee=info['referee'], round=int(info['round']), time=time)

    def _parse_sub_fight(self, row):
        td = row.findAll('td')
        left, right = td[1].a, td[3].a
        left_fighter = Fighter(left['href'], name=left.text)
        right_fighter = Fighter(right['href'], name=right.text)
        fighters = (left_fighter, right_fighter)
        result = td[1].find('span', {'class': _FINAL_RESULT_RE})
        if result is None:
            return Fight(event=self, fighters=fighters, winner=None,
                    match=None, method=None, referee=None,
                    round=None, time=None)
        winner = self._fight_winner(result, left_fighter, right_fighter)
        return Fight(event=self,
                     fighters=fighters,
                     winner=winner,
                     match=int(td[0].text),
                     method=td[4].contents[0],
                     referee=td[4].contents[-1].text,
                     round=int(td[5].text),
                     time=self._parse_fight_time(td[6].text))

    def _parse_sub_fights(self, dom):
        table = dom.find('div', {'class': _EVENT_MATCH_RE}).table
        rows = table.findAll('tr', {'itemprop': _SUB_EVENT_RE})
        return [self._parse_sub_fight(row) for row in rows]

    def _load_properties(self):
        dom = Sherdog.fetch_and_parse_url(self.url)
        detail = dom.find('div', {'class': 'event_detail'})
        self.name = detail.span.text
        datestr = detail.find('meta', {'itemprop': 'startDate'})['content']
        self.date = iso8601.parse_date(datestr).date()
        location = detail.find('span', {'itemprop': 'location'}).text
        venue, location = location.split(',', 1)
        self.venue = venue.lstrip()
        self.location = location.lstrip()
        location_thumb = detail.find('span', {'class': 'author'})
        if location_thumb is not None:
            self.location_thumb_url = location_thumb.img['src']
        else:
            self.location_thumb_url = None
        org = dom.find('div', {'itemprop': 'attendee'})
        self.organization = Organization(org.a['href'], name=org.span.text)
        self.fights = [self._parse_main_fight(dom)]
        self.fights.extend(self._parse_sub_fights(dom))
        self.fights.reverse()

    @classmethod
    def search(cls, query):
        """
        Search for an arbitrary event by name.

        Arguments:
            query: A string name to search for.

        Returns:
            A list of `Event` objects matching the query.
        """
        query = urllib.quote(query.lower())
        dom = Sherdog.fetch_and_parse_url(cls.search_url_path_template % query)
        table = dom.find('table', {'class': 'fightfinder_result'})
        urls = [a['href'] for a in table.findAll('a')]
        return map(cls, filter(_EVENTS_URL_RE.match, urls))


class Sherdog(object):
    """
    A simple web-scraping API for Sherdog.com.
    """

    @classmethod
    def fetch_url(cls, path):
        """
        Fetches a URL from sherdog.com by its path
        """
        assert path.startswith('/')
        url = SHERDOG_URL + path
        handle = urllib.urlopen(url)
        data = handle.read()
        handle.close()
        return data

    @classmethod
    def fetch_and_parse_url(cls, path):
        """
        Fetches a URL from sherdog.com and returns a BeautifulSoup object
        representing the parsed dom.
        """
        assert path.startswith('/')
        result = cls.fetch_url(path)
        soup = BeautifulSoup(result)
        return soup

    @classmethod
    def get_fighter(cls, id_or_url):
        """
        Returns a `Fighter` object using either the numerical ID
        or the URL path on sherdog.com

        See `Fighter`.
        """
        return Fighter(id_or_url)

    @classmethod
    def get_event(cls, id_or_url):
        """
        Returns an `Event` object using either the numerical ID
        or the URL path on sherdog.com

        See `Event`.
        """
        return Event(id_or_url)

    @classmethod
    def get_organization(cls, id_or_url):
        """
        Returns an `Organization` object using either its numerical ID
        or the URL path on sherdog.com

        See `Organization`.
        """
        return Organization(id_or_url)

    @classmethod
    def search_events(cls, name):
        """
        Searches for events by name.

        Returns:
            A list of `Event` objects.
        """
        return Event.search(name)

    @classmethod
    def search_organizations(cls, name):
        """
        Searches for organizations by name.

        Returns:
            A list of `Organization` objects.
        """
        return Organization.search(name)

    @classmethod
    def search_fighters(cls, name):
        """
        Searches for fighters by name.

        Returns:
            A list of `Fighter` objects.
        """
        return Fighter.search(name)
