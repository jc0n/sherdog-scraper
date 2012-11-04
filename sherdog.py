"""
Module for scraping sherdog.com for information about
mixed martial arts (MMA) fighters, fights, organizations, and events.
"""

import abc
import json
import math
import re
import string
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


def pick_winner(result, left_fighter, right_fighter):
    if result.text == u'draw':
        return None
    return left_fighter if result.text == u'win' else right_fighter


def parse_fight_time(timestr):
    if timestr and ':' in timestr:
        minutes, seconds = timestr.split(':', 1)
        return timedelta(minutes=int(minutes), seconds=int(seconds))


def clean_nickname(nickstr):
    if nickstr:
        return nickstr.strip('\'"' + string.whitespace)


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
    _object_cache = WeakValueDictionary()

    # whether or not the object identified by id or url exists on sherdog
    exists = None

    @property
    def full_url(self):
        """
        The absolute url on sherdog.com which corresponds with the object.
        Example: http://www.sherdog.com/events/BKF-2-Brazilian-King-Fighter-2-25419
        """
        return SHERDOG_URL + self.url

    def __new__(cls, id_or_url, *args, **kwargs):
        """
        Hook into Sherdog object creation and re-use existing objects if available in order to
        prevent hitting the website more often than necessary. Uses a weakref dictionary to
        hold onto objects as long as they are available.
        """
        if isinstance(id_or_url, basestring):
            id = int(id_or_url[id_or_url.rfind('-') + 1:])
        else:
            id = int(id_or_url)

        key = (type(cls), id)
        obj = cls._object_cache.get(key, None)
        if obj is None:
            obj = super(LazySherdogObject, cls).__new__(cls)
            obj.id = id
            obj.url = cls._url_path % id
            cls._object_cache[key] = obj

        for key, value in kwargs.iteritems():
            setattr(obj, key, value)

        return obj

    def __getattr__(self, key):
        if self.exists is False:
            raise self.DoesNotExist(self.full_url)
        if not self._lazy:
            raise AttributeError(key)

        self.load_properties()
        return getattr(self, key)

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __eq__(self, other):
        assert isinstance(other, LazySherdogObject)
        return self.url == other.url

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return repr(self.name)

    def __str__(self):
        return str(self.name)

    def load_properties(self):
        if not self._lazy:
            return

        self._lazy = False
        try:
            dom = _fetch_and_parse_url(self.url)
        except ObjectDoesNotExist:
            self.exists = False
            raise self.DoesNotExist(self.full_url)

        self.exists = True
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
        self.name = dom.find('h2', {'itemprop': 'name'}).text
        self.description = dom.find('div', {'class': 'data', 'itemprop': 'description'}).text

        self.events = []
        table = dom.find('table', class_='event')
        for row in table.find_all('tr', class_=_EVEN_ODD_RE):
            datestr = row.find('meta', {'itemprop': 'startDate'})['content']
            date = iso8601.parse_date(datestr)
            name = row.find('span', {'itemprop': 'name'}).text
            location = row.find('td', {'itemprop': 'location'}).text
            event = Event(row.a['href'], date=date, location=location, name=name)
            self.events.append(event)

    @classmethod
    def _search(cls, query):
        result = _fetch_url(cls._search_url_path % query)
        if not result:
            return ()
        data = json.loads(result)
        return [Organization(orgdict['id'], **orgdict) for orgdict in data['collection']]


class Fighter(LazySherdogObject):
    _url_path = '/fighter/X-%d'
    _search_url_path = '/stats/fightfinder?SearchTxt=%s'

    @property
    def age(self):
        "An integer for the fighters age (in years)."
        if not self.birthday:
            return None
        seconds = (datetime.now().date() - self.birthday).total_seconds()
        return int(math.floor(seconds / _SECONDS_IN_YEAR))

    def fights_in_common(self, other_fighter):
        assert isinstance(other_fighter, Fighter)
        result = list(set(self.fights) & set(other_fighter.fights))
        result.sort()
        return result

    @classmethod
    def _search(cls, query):
        dom = _fetch_and_parse_url(cls._search_url_path % query)
        if dom is None:
            return ()
        table = dom.find('table', class_='fightfinder_result')
        if table is None:
            return ()

        results = []
        for row in table.find_all('tr'):
            a = row.a
            if a is not None and _FIGHTER_URL_RE.match(a['href']):
                td = row.find_all('td')
                fighter = cls(a['href'],
                        name=a.text,
                        nickname=clean_nickname(td[2].text),
                        height=td[3].strong.text,
                        weight=td[4].strong.text,
                        association=td[5].text)
                results.append(fighter)
        return results

    def _load_properties(self, dom):
        self.name = dom.find('span', class_='fn').text.strip()

        nickname = dom.find('span', class_='nickname')
        self.nickname = clean_nickname(nickname.text) if nickname else None

        association = dom.find('span', {'itemprop': 'memberOf'})
        self.association = association.a.text.strip() if association else None

        image = dom.find('img', {'class': 'profile_image photo', 'itemprop': 'image'})
        self.image_url = image.get('src', None) if image else None


        self.birthday = None
        birthday = dom.find('span', {'itemprop': 'birthDate'})
        if birthday and birthday.text and '-' in birthday.text:
            self.birthday = datetime.strptime(birthday.text.strip(), "%Y-%m-%d").date()

        birthplace = dom.find('span', class_='item birthplace')
        self.city = birthplace.find('span', class_='locality').text
        self.country = birthplace.find('strong', {'itemprop': 'nationality'}).text
        self.country_flag_url = birthplace.img['src'] if birthplace.img else None

        self.height = dom.find('span', class_='item height').strong.text
        self.weight = dom.find('span', class_='item weight').strong.text
        self.weight_class = dom.find('h6', class_='item wclass').strong.text

        win_graph = dom.find('div', class_='bio_graph')
        counter = win_graph.find('span', class_='counter')
        self.wins = int(counter.text)

        lose_graph = dom.find('div', class_='bio_graph loser')
        counter = lose_graph.find('span', class_='counter')
        self.losses = int(counter.text)

        self.fights = []

        def fight_history(tag):
            if tag.name != 'div':
                return False
            try:
                heading = tag.h2.text
            except AttributeError:
                return False
            else:
                return heading.strip().lower() == 'fight history'

        fight_history = dom.find(fight_history, class_='module fight_history')
        if fight_history is not None:
            table = fight_history.table.tbody
            for row in table.find_all('tr', class_=_EVEN_ODD_RE):
                td = row.find_all('td')
                # right result (win, loss, draw)
                fight_result = row.find('span', {'class': _FINAL_RESULT_RE})

                # parse event info
                event_link = row.find('a', {'href': _EVENTS_URL_RE})
                event = Event(event_link['href'], name=event_link.text)

                # parse event date
                event_date = td[2].find('span', {'class': 'sub_line'})
                if event_date:
                    datestr = event_date.text.strip()
                    event.date = datetime.strptime(datestr, '%b / %d / %Y')

                # parse opponent
                opponent_link = row.find('a', {'href': _FIGHTER_URL_RE})
                opponent = Fighter(opponent_link['href'], name=opponent_link.text)

                # victory method, referee and round
                victory_method, referee = list(td[3].strings)[:2]
                round = int(td[4].text) if td[4].text else None

                fight = Fight(
                    event=event,
                    fighters=frozenset((self, opponent)),
                    referee=referee,
                    victory_method=victory_method,
                    round=round,
                    time=parse_fight_time(td[5].text),
                    winner=pick_winner(fight_result, self, opponent))
                self.fights.append(fight)


class Fight(namedtuple('Fight', ('event',
                                 'fighters',
                                 'referee',
                                 'victory_method',
                                 'round',
                                 'time',
                                 'winner'))):

    def __hash__(self):
        return hash((self.fighters, self.event))

    def __eq__(self, other):
        return self.fighters == other.fighters and self.event == other.event

    def __cmp__(self, other):
        if not isinstance(other, Fight):
            raise TypeError("cannot compare Fight with %s" % type(other))
        return cmp(self.event, other.event)

    def __str__(self):
        return u' vs. '.join([f.name.split(None, 1)[-1].title()
                                for f in self.fighters])



class Event(LazySherdogObject):
    _url_path = '/events/X-%d'
    _search_url_path = '/stats/fightfinder?SearchTxt=%s'

    def __cmp__(self, other):
        if not isinstance(other, Event):
            raise TypeError("cannot compare Event with %s" % type(other))
        return cmp(self.date, other.date)

    def _load_properties(self, dom):
        def parse_main_fight(dom):
            left = dom.find('div', class_='fighter left_side').h3.a
            left_fighter = Fighter(left['href'], name=left.text)

            right = dom.find('div', class_='fighter right_side').h3.a
            right_fighter = Fighter(right['href'], name=right.text)

            fighters = frozenset((left_fighter, right_fighter))
            result = dom.find('span', class_=_FINAL_RESULT_RE)
            if result is None:
                return Fight(
                        event=self,
                        fighters=fighters,
                        referee=None,
                        victory_method=None,
                        round=None,
                        time=None,
                        winner=None)

            # parse match, method, ref, round, time
            td = dom.find('table', class_='resume').find_all('td')
            info = dict((x.contents[0].text.lower(), x.contents[-1].lstrip()) for x in td)
            return Fight(
                    event=self,
                    fighters=fighters,
                    referee=info['referee'],
                    victory_method=info['method'],
                    round=int(info['round']),
                    time=parse_fight_time(info['time']),
                    winner=pick_winner(result, left_fighter, right_fighter))

        def parse_fight(row):
            td = row.find_all('td')
            left, right = td[1].a, td[3].a
            left_fighter = Fighter(left['href'], name=left.text)
            right_fighter = Fighter(right['href'], name=right.text)
            fighters = frozenset((left_fighter, right_fighter))
            result = td[1].find('span', class_=_FINAL_RESULT_RE)
            if result is None:
                return Fight(
                        event=self,
                        fighters=fighters,
                        referee=None,
                        victory_method=None,
                        round=None,
                        time=None,
                        winner=None)
            else:
                return Fight(
                        event=self,
                        fighters=fighters,
                        referee=td[4].contents[-1].text,
                        victory_method=td[4].contents[0],
                        round=int(td[5].text),
                        time=parse_fight_time(td[6].text),
                        winner=pick_winner(result, left_fighter, right_fighter))

        def parse_fights(dom):
            table = dom.find('div', class_='module event_match').table
            rows = table.find_all('tr', {'itemprop': 'subEvent'})
            return [parse_fight(row) for row in rows]

        detail = dom.find('div', class_='event_detail')
        self.name = detail.span.text

        datestr = detail.find('meta', {'itemprop': 'startDate'})['content']
        self.date = iso8601.parse_date(datestr).date()

        venue, location = detail.find('span', {'itemprop': 'location'}).text.split(',', 1)
        self.location = location.lstrip()
        self.location_thumb_url = detail.find('span', class_='author').img['src']
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
        if dom is None:
            return ()

        table = dom.find('table', class_='fightfinder_result')
        if table is None:
            return ()

        results = []
        for row in table.find_all('tr'):
            a = row.a
            if a is not None and _EVENTS_URL_RE.match(a['href']):
                td = row.find_all('td')
                event = Event(a['href'], name=a.text)
                results.append(event)

                datestr = ' '.join(td[0].stripped_strings)
                event.date = datetime.strptime(datestr, '%b %d %Y')

                org_link = td[2].a
                if org_link:
                    event.organization = Organization(org_link['href'], name=org_link.text)


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
