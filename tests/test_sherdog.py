#!/usr/bin/env python

from datetime import date, timedelta
from unittest import TestCase, main

from sherdog import Sherdog, Event, Organization, Fighter

FRANK_MIR_ID = 2329
FRANK_MIR_URL = '/fighter/Frank-Mir-2329'

JUNIOR_DOS_SANTOS_ID = 17272

UFC = Organization('Ultimate-Fighting-Championship-2')
UFC_ID = 2

UFC146 = Event('UFC-146-Dos-Santos-vs-Mir-20353')

class TestSherdog(TestCase):

    def test_get_fighter(self):
        for f in map(Sherdog.get_fighter, (FRANK_MIR_ID, FRANK_MIR_URL)):
            self.assertEquals(f.name, u'Frank Mir')
            self.assertEquals(f.birthday, date(1979, 5, 24))
            self.assertEquals(f.height, u'6\'3"')
            weight = f.weight.split()
            self.assertAlmostEquals(int(weight[0]), 260, delta=25)
            self.assertEquals(weight[1], u'lbs')
            self.assertEquals(f.city, u'Las Vegas, Nevada')
            self.assertEquals(f.country, u'United States')
            self.assertTrue(f.country_flag_url.endswith(u'/img/w/flags/us.png'))
            self.assertGreater(f.wins, 15)
            self.assertGreater(f.losses, 5)
            self.assertEquals(f.image_url,
                    u'http://www1.cdn.sherdog.com/image_crop/200/300/_images/fighter/20110412122006_20091214122837_IMG_5197.JPG')

            self.assertIn(UFC146, f.events)
            self.assertGreater(len(f.events), 21)

    def test_get_event(self):
        event = Sherdog.get_event('UFC-146-Dos-Santos-vs-Mir-20353')
        self.assertEquals(event.name, u'UFC 146 - Dos Santos vs. Mir')
        self.assertEquals(event.organization, UFC)
        self.assertEquals(event.date, date(2012, 5, 26))
        self.assertEquals(event.venue, u'MGM Grand Garden Arena')
        self.assertEquals(event.location, u'Las Vegas, Nevada, United States')
        self.assertEquals(len(event.fights), 12)

        frank = Fighter(FRANK_MIR_ID)
        junior = Fighter(JUNIOR_DOS_SANTOS_ID)
        main_fight = event.fights[-1]
        self.assertEquals(main_fight.fighters, (junior, frank))
        self.assertEquals(main_fight.winner, junior)
        self.assertEquals(main_fight.match, 12)
        self.assertEquals(main_fight.method, u'TKO (Punches)')
        self.assertEquals(main_fight.referee, u'Herb Dean')
        self.assertEquals(main_fight.round, 2)
        self.assertEquals(main_fight.time, timedelta(minutes=3, seconds=4))

        cain = Fighter('Cain-Velasquez-19102')
        bigfoot = Fighter('Antonio-Silva-12354')
        other_fight = event.fights[-2]
        self.assertEquals(other_fight.fighters, (cain, bigfoot))
        self.assertEquals(other_fight.winner, cain)
        self.assertEquals(other_fight.match, 11)
        self.assertEquals(other_fight.method, u'TKO (Punches)')
        self.assertEquals(other_fight.round, 1)
        self.assertEquals(other_fight.time, timedelta(minutes=3, seconds=36))
        self.assertEquals(other_fight.referee, u'Josh Rosenthal')

    def test_get_organization(self):
        org = Sherdog.get_organization(UFC_ID)
        self.assertEquals(org.name, u'Ultimate Fighting Championship')
        self.assertGreater(len(org.events), 170)
        self.assertIn(UFC146, org.events)

    def test_search_events(self):
        results = Sherdog.search_events('ufc 146')
        self.assertGreaterEqual(len(results), 1)
        self.assertEquals(results[0], UFC146)

    def test_search_organizations(self):
        results = Sherdog.search_organizations('ultimate fighting championship')
        self.assertGreaterEqual(len(results), 3)
        self.assertEquals(results[0], UFC)

        results = Sherdog.search_organizations('strikeforce')
        self.assertGreaterEqual(len(results), 1)
        self.assertEquals(results[0], Organization('Strikeforce-716'))

    def test_search_fighters(self):
        results = Sherdog.search_fighters('frank mir')
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0], Fighter(FRANK_MIR_ID))

        results = Sherdog.search_fighters('junior dos santos')
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0], Fighter(JUNIOR_DOS_SANTOS_ID))


if __name__ == '__main__':
    unittest.main()
