"""
API for scraping information about MMA fighters
and events from Sherdog.com
"""

import abc
import json
import re
import urllib

from collections import namedtuple
from datetime import timedelta
from weakref import WeakValueDictionary

# dependencies
import iso8601
from BeautifulSoup import BeautifulSoup

__author__ = 'John O\'Connor'

SHERDOG_URL = 'http://www.sherdog.com'

_EVENT_MATCH_RE = re.compile('module event_match')
_EVEN_ODD_RE = re.compile('^(even)|(odd)$')
_FIGHTER_LEFT_RE = re.compile('fighter left_side')
_FIGHTER_RIGHT_RE = re.compile('fighter right_side')
_FINAL_RESULT_RE = re.compile('^final_result')
_SUB_EVENT_RE = re.compile('subEvent')

__all__ = ('Sherdog', )

class LazySherdogObject(object):
    __metaclass__ = abc.ABCMeta
    _lazy = True
    _url_path = abc.abstractproperty()

    def __init__(self, sherdog, id_or_url=None, **kwargs):
        self._sherdog = sherdog
        if id_or_url is not None:
            if isinstance(id_or_url, basestring):
                self.url = id_or_url
                self.id = int(self.url[self.url.rfind('-') + 1:])
            else:
                self.id = int(id_or_url)
                self.url = self._url_path % self.id

        for key, value in kwargs.iteritems():
            setattr(self, key, value)

    def __getattr__(self, key):
        if not self._lazy:
            raise AttributeError(key)

        self._load_properties()
        self._lazy = False
        return getattr(self, key)

    def __getitem__(self, key):
        return getattr(self, key)

    @abc.abstractmethod
    def _load_properties(self):
        pass


class Organization(LazySherdogObject):
    _url_path = '/organizations/X-%d'
    _search_url_path = '/search/organizations/?q=%s'

    def _load_properties(self):
        dom = self._sherdog.fetch_and_parse_url(self.url)
        description = dom.find('div', {'class': 'data', 'itemprop': 'description'})
        self.description = description.text

        self.events = []
        table = dom.find('table', {'class': 'event'})
        rows = table.findAll('tr', {'class': _EVEN_ODD_RE})
        for row in rows:
            datestr = row.find('meta', {'itemprop': 'startDate'})['content']
            date = iso8601.parse_date(datestr)
            name = row.find('span', {'itemprop': 'name'}).text
            location = row.find('td', {'itemprop': 'location'}).text
            self.events.append(Event(self._sherdog, url=row.a['href'], date=date,
                    location=location, name=name))


    @classmethod
    def search(cls, query, sherdog=None):
        if sherdog is None:
            sherdog = Sherdog()
        query = urllib.quote(query.lower())
        result = sherdog.fetch_url(self._search_url_path % query)
        data = json.loads(result)
        return [Organization(self, **orgdict) for orgdict in data['collection']]

    def __repr__(self):
        return repr(self.name)


class Fighter(LazySherdogObject):
    _url_path = '/fighter/X-%d'

    def __repr__(self):
        return repr(self.name)

    @property
    def full_url(self):
        return SHERDOG_URL + self.url

    def _load_properties(self):
        # TODO
        pass


class Fight(namedtuple('Fight', ('event', 'fighters', 'match',
                                 'method', 'referee', 'round',
                                 'time', 'winner'))):

    def __repr__(self):
        return u' vs. '.join([f.name for f in self.fighters])


class Event(LazySherdogObject):

    _url_path = '/events/X-%d'
    _search_url_path = '/stats/fightfinder?SearchTxt=%s'

    @property
    def full_url(self):
        return SHERDOG_URL + self.url

    def __repr__(self):
        return repr(self.name)

    def _parse_fight_time(self, timestr):
        if not timestr:
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
        left_fighter = Fighter(self._sherdog, left['href'], name=left.text)

        right = dom.find('div', {'class': _FIGHTER_RIGHT_RE}).h3.a
        right_fighter = Fighter(self._sherdog, right['href'], name=right.text)

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
                match=info['match'], method=info['method'], referee=info['referee'],
                round=info['round'], time=time)

    def _parse_sub_fight(self, row):
        td = row.findAll('td')
        left, right = td[1].a, td[3].a
        left_fighter = Fighter(self._sherdog, left['href'], name=left.text)
        right_fighter = Fighter(self._sherdog, right['href'], name=right.text)
        fighters = (left_fighter, right_fighter)
        result = td[1].find('span', {'class': _FINAL_RESULT_RE})
        if result is None:
            return Fight(event=self, fighters=fighters, winner=None,
                    match=None, method=None, referee=None,
                    round=None, time=None)

        return Fight(event=self,
                     fighters=fighters,
                     winner=self._fight_winner(result, left_fighter, right_fighter),
                     match=td[0].text,
                     method=td[4].contents[0],
                     referee=td[4].contents[-1],
                     round=int(td[5].text),
                     time=self._parse_fight_time(td[6].text))

    def _parse_sub_fights(self, dom):
        table = dom.find('div', {'class': _EVENT_MATCH_RE}).table
        rows = table.findAll('tr', {'itemprop': _SUB_EVENT_RE})
        return [self._parse_sub_fight(row) for row in rows]

    def _load_properties(self):
        dom = self._sherdog.fetch_and_parse_url(self.url)
        detail = dom.find('div', {'class': 'event_detail'})
        self.name = detail.span.text
        datestr = detail.find('meta', {'itemprop': 'startDate'})['content']
        self.date = iso8601.parse_date(datestr)
        location = detail.find('span', {'itemprop': 'location'}).text
        venue, location = location.split(',', 1)
        self.location = location
        self.location_thumb_url = detail.find('span', {'class': 'author'}).img['src']
        self.venue = venue.lstrip()
        org = dom.find('div', {'itemprop': 'attendee'})
        self.organization = Organization(self._sherdog, org.a['href'], name=org.span.text)
        self.fights = [self._parse_main_fight(dom)]
        self.fights.extend(self._parse_sub_fights(dom))

    @classmethod
    def search(cls, query, sherdog=None):
        if sherdog is None:
            sherdog = Sherdog()
        query = urllib.quote(query.lower())
        dom = sherdog.fetch_and_parse_url(self._search_url_path % query)
        table = dom.find('table', {'class': 'fightfinder_result'})
        links = table.findAll('a')
        return [cls(sherdog, a['href']) for a in links]


class Sherdog(object):
    def __init__(self):
        self._cache = WeakValueDictionary()

    def fetch_url(self, path):
        assert path.startswith('/')
        url = SHERDOG_URL + path
        handle = urllib.urlopen(url)
        data = handle.read()
        handle.close()
        return data

    def fetch_and_parse_url(self, path):
        assert path.startswith('/')
        soup = self._cache.get(path)
        if not soup:
            result = self.fetch_url(path)
            soup = BeautifulSoup(result)
            self._cache[path] = soup
        return soup

    def get_fighter(self, id_or_url):
        return Fighter(self, id_or_url)

    def get_event(self, id_or_url):
        return Event(self, id_or_url)

    def get_organization(self, id_or_url):
        return Organization(self, id_or_url)

    def search_events(self, query):
        return Event.search(query, sherdog=self)

    def search_organizations(self, query):
        return Organization.search(query, sherdog=self)


import pdb
s = Sherdog()
print s.search_events('ufc 100')
print s.search_events('ufc 149')
