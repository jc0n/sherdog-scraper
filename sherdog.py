"""
API for scraping information about MMA fighters
and events from Sherdog.com
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
from BeautifulSoup import BeautifulSoup

__author__ = 'John O\'Connor'
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
    __metaclass__ = abc.ABCMeta
    _lazy = True
    _url_path = abc.abstractproperty()

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
        pass


class Organization(LazySherdogObject):
    _url_path = '/organizations/X-%d'
    _search_url_path = '/search/organizations/?q=%s'

    def _load_properties(self):
        dom = Sherdog.fetch_and_parse_url(self.url)

        name = dom.find('h2', {'itemprop': 'name'})
        self.name = name.text if name else None

        description = dom.find('div', {'class': 'data', 'itemprop': 'description'})
        self.description = description.text if description else None

        self.events = []
        table = dom.find('table', {'class': 'event'})
        rows = table.findAll('tr', {'class': _EVEN_ODD_RE})
        for row in rows:
            datestr = row.find('meta', {'itemprop': 'startDate'})['content']
            date = iso8601.parse_date(datestr)
            name = row.find('span', {'itemprop': 'name'}).text
            location = row.find('td', {'itemprop': 'location'}).text
            event = Event(row.a['href'], date=date, location=location, name=name)
            self.events.append(event)

    @classmethod
    def search(cls, query):
        query = urllib.quote(query.lower())
        result = Sherdog.fetch_url(cls._search_url_path % query)
        data = json.loads(result)
        return [Organization(id_or_url=orgdict['id'], **orgdict) for orgdict in data['collection']]

    def __repr__(self):
        return repr(self.name)


class Fighter(LazySherdogObject):
    _url_path = '/fighter/X-%d'
    _search_url_path = '/stats/fightfinder?SearchTxt=%s'

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
        query = urllib.quote(query.lower())
        dom = Sherdog.fetch_and_parse_url(cls._search_url_path % query)
        table = dom.find('table', {'class': 'fightfinder_result'})
        urls = [a['href'] for a in table.findAll('a')]
        return map(cls, filter(_FIGHTER_URL_RE.match, urls))

    def _load_properties(self):
        dom = Sherdog.fetch_and_parse_url(self.url)

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
            event_links = content.table.findAll('a', {'href': _EVENTS_URL_RE})
            self.events = [Event(a['href']) for a in event_links]


class Fight(namedtuple('Fight', ('event', 'fighters', 'match',
                                 'method', 'referee', 'round',
                                 'time', 'winner'))):

    def __repr__(self):
        return u' vs. '.join([f.name.split(None, 1)[-1].title()
                                for f in self.fighters])


class Event(LazySherdogObject):

    _url_path = '/events/X-%d'
    _search_url_path = '/stats/fightfinder?SearchTxt=%s'

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
                match=int(info['match']), method=info['method'], referee=info['referee'],
                round=int(info['round']), time=time)

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

        return Fight(event=self,
                     fighters=fighters,
                     winner=self._fight_winner(result, left_fighter, right_fighter),
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
        self.location = location.lstrip()
        self.location_thumb_url = detail.find('span', {'class': 'author'}).img['src']
        self.venue = venue.lstrip()
        org = dom.find('div', {'itemprop': 'attendee'})
        self.organization = Organization(org.a['href'], name=org.span.text)
        self.fights = [self._parse_main_fight(dom)]
        self.fights.extend(self._parse_sub_fights(dom))
        self.fights.reverse()

    @classmethod
    def search(cls, query):
        query = urllib.quote(query.lower())
        dom = Sherdog.fetch_and_parse_url(cls._search_url_path % query)
        table = dom.find('table', {'class': 'fightfinder_result'})
        urls = [a['href'] for a in table.findAll('a')]
        return map(cls, filter(_EVENTS_URL_RE.match, urls))


class Sherdog(object):

    @classmethod
    def fetch_url(cls, path):
        assert path.startswith('/')
        url = SHERDOG_URL + path
        handle = urllib.urlopen(url)
        data = handle.read()
        handle.close()
        return data

    @classmethod
    def fetch_and_parse_url(cls, path):
        assert path.startswith('/')
        result = cls.fetch_url(path)
        soup = BeautifulSoup(result)
        return soup

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
