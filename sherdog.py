"""
Module for scraping sherdog.com for information about
mixed martial arts (MMA) fighters, fights, organizations, and events.
"""

import abc
import json
import math
import re
import urllib

from collections import namedtuple
from datetime import timedelta, datetime
from weakref import WeakValueDictionary

# dependencies
import iso8601
from bs4 import BeautifulSoup

__author__ = 'John O\'Connor'
__version__ = '0.0.2'

__all__ = ('Sherdog', 'Event', 'Fight', 'Fighter', 'Organization', 'SHERDOG_URL')

SHERDOG_URL = 'http://www.sherdog.com'


_EVEN_ODD_RE = re.compile('^(even)|(odd)$')
_FINAL_RESULT_RE = re.compile('^final_result')

_EVENTS_URL_RE = re.compile('^/events/')
_FIGHTER_URL_RE = re.compile('^/fighter/')

_SECONDS_IN_YEAR = 60 * 60 * 24 * 365

class ObjectDoesNotExist(Exception):
    """
    Base exception raised when objects cannot be found.
    """
    pass


def _fetch_url(path):
    assert path.startswith('/')
    url = SHERDOG_URL + path
    handle = urllib.urlopen(url)
    if handle.code == 404:
        raise ObjectDoesNotExist(url)
    data = handle.read()
    handle.close()
    return data


def _fetch_and_parse_url(path):
    assert path.startswith('/')
    result = _fetch_url(path)
    soup = BeautifulSoup(result)
    return soup


class SherdogObjectMetaclass(abc.ABCMeta):
    def __new__(cls, name, bases, attrs):
        class DoesNotExist(ObjectDoesNotExist):
            """
            Raised when an object which is a subclass of this metaclass does not exist.
            """
            pass

        attrs['DoesNotExist'] = DoesNotExist
        return super(SherdogObjectMetaclass, cls).__new__(cls, name, bases, attrs)

class LazySherdogObject(object):
    """
    An abstract base class for Sherdog objects which helps facilitate the lazy
    loading of object properties.
    """
    __metaclass__ = SherdogObjectMetaclass
    _lazy = True
    _url_path = abc.abstractproperty()

    @property
    def full_url(self):
        """
        The absolute url on sherdog.com which corresponds with the object.
        Example: http://www.sherdog.com/events/BKF-2-Brazilian-King-Fighter-2-25419
        """
        return SHERDOG_URL + self.url

    def __init__(self, id_or_url, **kwargs):
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

        if isinstance(id_or_url, basestring):
            self.id = int(id_or_url[id_or_url.rfind('-') + 1:])
        else:
            self.id = int(id_or_url)

        self.url = self._url_path % self.id

    def __getattr__(self, key):
        if not self._lazy:
            raise AttributeError(key)

        self._lazy = False
        self.load_properties()
        return getattr(self, key)

    def __getitem__(self, key):
        return getattr(self, key)

    def __eq__(self, other):
        assert isinstance(other, LazySherdogObject)
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        return str(self.name)

    def load_properties(self):
        try:
            dom = _fetch_and_parse_url(self.url)
        except ObjectDoesNotExist:
            raise self.DoesNotExist(self.full_url)

        self._load_properties(dom)

    @abc.abstractmethod
    def _load_properties(self, dom):
        pass

    @classmethod
    def search(cls, query):
        if not query:
            raise ValueError("query must not be empty.")
        query = urllib.quote(query.lower())
        return cls._search(query)

    @abc.abstractmethod
    def _search(self, query):
        pass


class Organization(LazySherdogObject):
    _url_path = '/organizations/X-%d'
    _search_url_path = '/search/organizations/?q=%s'

    def _load_properties(self, dom):
        name = dom.find('h2', {'itemprop': 'name'})
        self.name = name.text if name else None

        description = dom.find('div', {'class': 'data', 'itemprop': 'description'})
        self.description = description.text if description else None

        self.events = []
        table = dom.find('table', {'class': 'event'})
        rows = table.find_all('tr', {'class': _EVEN_ODD_RE})
        for row in rows:
            datestr = row.find('meta', {'itemprop': 'startDate'})['content']
            date = iso8601.parse_date(datestr)
            name = row.find('span', {'itemprop': 'name'}).text
            location = row.find('td', {'itemprop': 'location'}).text
            event = Event(row.a['href'], date=date, location=location, name=name)
            self.events.append(event)

    @classmethod
    def _search(cls, query):
        result = _fetch_url(cls._search_url_path % query)
        data = json.loads(result)
        return [Organization(orgdict['id'], **orgdict) for orgdict in data['collection']]


class Fighter(LazySherdogObject):
    _url_path = '/fighter/X-%d'
    _search_url_path = '/stats/fightfinder?SearchTxt=%s'

    @property
    def age(self):
        "An integer for the fighters age (in years)."
        seconds = (datetime.now() - self.birthday).total_seconds()
        return int(math.floor(seconds / _SECONDS_IN_YEAR))

    @property
    def total_fights(self):
        return len(self.events)

    @classmethod
    def _search(cls, query):
        dom = _fetch_and_parse_url(cls._search_url_path % query)
        table = dom.find('table', {'class': 'fightfinder_result'})
        if not table:
            return ()

        urls = [a['href'] for a in table.find_all('a')]
        return map(cls, filter(_FIGHTER_URL_RE.match, urls))

    def _load_properties(self, dom):
        image = dom.find('img', {'class': 'profile_image photo', 'itemprop': 'image'})
        self.image_url = image['src'] if image else None

        name = dom.find('span', {'class': 'fn'})
        self.name = name.text if name else None

        nickname = dom.find('span', {'class': 'nickname'})
        self.nickname = nickname.text.strip('\'"') if nickname else None

        birthday = dom.find('span', {'itemprop': 'birthDate'})
        if birthday and '-' in birthday.text:
            self.birthday = datetime.strptime(birthday.text, "%Y-%m-%d").date()
        else:
            self.birthday = None

        birthplace = dom.find('span', {'class': 'item birthplace'})
        if birthplace:
            city = birthplace.find('span', {'class': 'locality'})
            self.city = city.text if city else None
            country = birthplace.find('strong', {'itemprop': 'nationality'})
            self.country = country.text if country else None
            self.country_flag_url = birthplace.img['src'] if birthplace.img else None
        else:
            self.city = self.country = self.country_flag_url = None

        height = dom.find('span', {'class': 'item height'})
        self.height = height.strong.text if height and hasattr(height, 'strong') else None

        weight = dom.find('span', {'class': 'item weight'})
        self.weight = weight.strong.text if weight and hasattr(weight, 'strong') else None

        wclass = dom.find('h6', {'class': 'item wclass'})
        self.weight_class = wclass.strong.text if wclass and hasattr(wclass, 'strong') else None

        win_graph = dom.find('div', {'class': 'bio_graph'})
        if win_graph:
            counter = win_graph.find('span', {'class': 'counter'})
            self.wins = int(counter.text) if counter else 0
        else:
            self.wins = None

        lose_graph = dom.find('div', {'class': 'bio_graph loser'})
        if lose_graph:
            counter = lose_graph.find('span', {'class': 'counter'})
            self.losses = int(counter.text) if counter else 0
        else:
            self.losses = None

        content = dom.find('div', {'class': 'content table'})
        if content and hasattr(content, 'table'):
            event_links = content.table.find_all('a', {'href': _EVENTS_URL_RE})
            self.events = [Event(a['href']) for a in event_links]


class Fight(namedtuple('Fight', ('event',
                                 'fighters',
                                 'referee',
                                 'victory_method',
                                 'victory_round',
                                 'victory_time',
                                 'winner'))):

    def __hash__(self):
        return hash(self.fighters + (self.event, ))

    def __eq__(self, other):
        return (self.fighters == other.fighters and
                self.event == other.event)

    def __str__(self):
        return u' vs. '.join([f.name.split(None, 1)[-1].title()
                                for f in self.fighters])


class Event(LazySherdogObject):
    _url_path = '/events/X-%d'
    _search_url_path = '/stats/fightfinder?SearchTxt=%s'

    def _load_properties(self, dom):
        def parse_time(timestr):
            if timestr and ':' in timestr:
                minutes, seconds = timestr.split(':', 1)
                return timedelta(minutes=int(minutes), seconds=int(seconds))

        def parse_winner(result, left, right):
            if result.text == u'draw':
                return None
            elif result.text == u'win':
                return left
            else:
                return right

        def parse_main_fight(dom):
            left = dom.find('div', {'class': 'fighter left_side'}).h3.a
            left_fighter = Fighter(left['href'], name=left.text)

            right = dom.find('div', {'class': 'fighter right_side'}).h3.a
            right_fighter = Fighter(right['href'], name=right.text)

            fighters = (left_fighter, right_fighter)
            result = dom.find('span', {'class': _FINAL_RESULT_RE})
            if result is None:
                return Fight(
                        event=self,
                        fighters=fighters,
                        referee=None,
                        victory_method=None,
                        victory_round=None,
                        victory_time=None,
                        winner=None)

            # parse match, method, ref, round, time
            td = dom.find('table', {'class':'resume'}).find_all('td')
            keys = [x.contents[0].text.lower() for x in td]
            values = [x.contents[-1].lstrip() for x in td]
            info = dict(zip(keys, values))
            return Fight(
                    event=self,
                    fighters=fighters,
                    referee=info['referee'],
                    victory_method=info['method'],
                    victory_round=int(info['round']),
                    victory_time=parse_time(info['time']),
                    winner=parse_winner(result, left_fighter, right_fighter))

        def parse_fight(row):
            td = row.find_all('td')
            left, right = td[1].a, td[3].a
            left_fighter = Fighter(left['href'], name=left.text)
            right_fighter = Fighter(right['href'], name=right.text)
            fighters = (left_fighter, right_fighter)
            result = td[1].find('span', {'class': _FINAL_RESULT_RE})
            if result is None:
                return Fight(
                        event=self,
                        fighters=fighters,
                        referee=None,
                        victory_method=None,
                        victory_round=None,
                        victory_time=None,
                        winner=None)
            else:
                return Fight(
                        event=self,
                        fighters=fighters,
                        referee=td[4].contents[-1].text,
                        victory_method=td[4].contents[0],
                        victory_round=int(td[5].text),
                        victory_time=parse_time(td[6].text),
                        winner=parse_winner(result, left_fighter, right_fighter))

        def parse_fights(dom):
            table = dom.find('div', {'class': 'module event_match'}).table
            rows = table.find_all('tr', {'itemprop': 'subEvent'})
            return [parse_fight(row) for row in rows]

        detail = dom.find('div', {'class': 'event_detail'})
        self.name = detail.span.text

        datestr = detail.find('meta', {'itemprop': 'startDate'})['content']
        self.date = iso8601.parse_date(datestr).date()

        location = detail.find('span', {'itemprop': 'location'}).text
        venue, location = location.split(',', 1)
        self.location = location.lstrip()
        self.location_thumb_url = detail.find('span', {'class': 'author'}).img['src']
        self.venue = venue.lstrip()

        org = dom.find('div', {'itemprop': 'attendee'})
        self.organization = Organization(org.a['href'], name=org.span.text)

        fights = [parse_main_fight(dom)]
        fights.extend(parse_fights(dom))
        fights.reverse()
        self.fights = fights

    @classmethod
    def _search(cls, query):
        dom = _fetch_and_parse_url(cls._search_url_path % query)
        table = dom.find('table', {'class': 'fightfinder_result'})
        if not table:
            return ()
        urls = [a['href'] for a in table.find_all('a')]
        return map(cls, filter(_EVENTS_URL_RE.match, urls))


class Sherdog:
    def __init__(self):
        raise TypeError("Sherdog class is not intended to be instantiated.")

    @classmethod
    def get_fighter(cls, id_or_url):
        return Fighter(id_or_url)

    @classmethod
    def get_event(cls, id_or_url):
        return Event(id_or_url)

    @classmethod
    def get_organization(cls, id_or_url):
        return Organization(id_or_url)

    @classmethod
    def search_events(cls, query):
        return Event.search(query)

    @classmethod
    def search_organizations(cls, query):
        return Organization.search(query)

    @classmethod
    def search_fighters(cls, query):
        return Fighter.search(query)
