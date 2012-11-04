#!/usr/bin/env python

from datetime import date, timedelta
from unittest import TestCase, main

from sherdog import Sherdog, Event, Organization, Fighter


class TestSherdog(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.frank_mir_id = 2329
        cls.frank_mir_url = '/fighter/Frank-Mir-2329'
        cls.frank_mir = Fighter(cls.frank_mir_id)

        cls.junior_dos_santos_id = 17272

        cls.ufc = Organization('Ultimate-Fighting-Championship-2')
        cls.ufc_id = 2

        cls.ufc146 = Event('UFC-146-Dos-Santos-vs-Mir-20353')

    def test_get_fighter(self):
        for f in map(Sherdog.get_fighter, (self.frank_mir_id, self.frank_mir_url)):
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

            self.assertIn(self.ufc146, f.events)
            self.assertGreater(len(f.events), 21)

    def test_get_event(self):
        event = Sherdog.get_event('UFC-146-Dos-Santos-vs-Mir-20353')
        self.assertEquals(event.name, u'UFC 146 - Dos Santos vs. Mir')
        self.assertEquals(event.organization, self.ufc)
        self.assertEquals(event.date, date(2012, 5, 26))
        self.assertEquals(event.venue, u'MGM Grand Garden Arena')
        self.assertEquals(event.location, u'Las Vegas, Nevada, United States')
        self.assertEquals(len(event.fights), 12)

        frank = Fighter(self.frank_mir_id)
        junior = Fighter(self.junior_dos_santos_id)
        main_fight = event.fights[-1]
        self.assertEquals(main_fight.fighters, (junior, frank))
        self.assertEquals(main_fight.winner, junior)
        self.assertEquals(main_fight.victory_method, u'TKO (Punches)')
        self.assertEquals(main_fight.referee, u'Herb Dean')
        self.assertEquals(main_fight.victory_round, 2)
        self.assertEquals(main_fight.victory_time, timedelta(minutes=3, seconds=4))

        cain = Fighter('Cain-Velasquez-19102')
        bigfoot = Fighter('Antonio-Silva-12354')
        other_fight = event.fights[-2]
        self.assertEquals(other_fight.fighters, (cain, bigfoot))
        self.assertEquals(other_fight.winner, cain)
        self.assertEquals(other_fight.victory_method, u'TKO (Punches)')
        self.assertEquals(other_fight.victory_round, 1)
        self.assertEquals(other_fight.victory_time, timedelta(minutes=3, seconds=36))
        self.assertEquals(other_fight.referee, u'Josh Rosenthal')

    def test_get_organization(self):
        org = Sherdog.get_organization(self.ufc_id)
        self.assertEquals(org.name, u'Ultimate Fighting Championship')
        self.assertGreater(len(org.events), 170)
        self.assertIn(self.ufc146, org.events)

    def test_search_events(self):
        results = Sherdog.search_events('ufc 146')
        self.assertGreaterEqual(len(results), 1)
        self.assertEquals(results[0], self.ufc146)

    def test_search_organizations(self):
        results = Sherdog.search_organizations('ultimate fighting championship')
        self.assertGreaterEqual(len(results), 3)
        self.assertEquals(results[0], self.ufc)

        results = Sherdog.search_organizations('strikeforce')
        self.assertGreaterEqual(len(results), 1)
        self.assertEquals(results[0], Organization('Strikeforce-716'))

    def test_search_fighters(self):
        results = Sherdog.search_fighters('frank mir')
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0], Fighter(self.frank_mir_id))

        results = Sherdog.search_fighters('junior dos santos')
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0], Fighter(self.junior_dos_santos_id))

    def test_object_cache(self):
        tito1 = Sherdog.search_fighters('tito ortiz')[0]
        tito2 = Sherdog.search_fighters('tito ortiz')[0]
        self.assertIs(tito1, tito2)
        self.assertEquals(tito1.name, u'Tito Ortiz')
        self.assertIs(tito1.name, tito2.name)

        ufc146 = Sherdog.search_events('ufc 146')[0]
        self.assertIs(ufc146, self.ufc146)
        self.assertIsNot(ufc146, tito1)


class TestSherdogErrors(TestCase):

    def test_exception_sanity(self):
        self.assertNotEquals(Fighter.DoesNotExist, Event.DoesNotExist)
        self.assertNotEquals(Event.DoesNotExist, Organization.DoesNotExist)

    def test_fighter_not_exists(self):
        f = Fighter(0)
        self.assertRaises(Fighter.DoesNotExist, lambda: f.name)

        f = Fighter('/asdf-0')
        self.assertRaises(Fighter.DoesNotExist, lambda: f.name)

    def test_event_not_exists(self):
        e = Event(0)
        self.assertRaises(Event.DoesNotExist, lambda: e.name)

    def test_organization_not_exists(self):
        o = Organization(0)
        self.assertRaises(Organization.DoesNotExist, lambda: o.name)

    def test_empty_query(self):
        self.assertRaises(ValueError, Sherdog.search_fighters, '')
        self.assertRaises(ValueError, Sherdog.search_events, '')
        self.assertRaises(ValueError, Sherdog.search_organizations, '')

        self.assertRaises(ValueError, Fighter.search, '')
        self.assertRaises(ValueError, Event.search, '')
        self.assertRaises(ValueError, Organization.search, '')

    def test_empty_fighter_results(self):
        results = Sherdog.search_fighters('zzz')
        self.assertEquals(len(results), 0)
        self.assertSequenceEqual(results, [])

    def test_invalid_attribute(self):
        frank_mir_id = 2329
        f = Fighter(frank_mir_id)

        self.assertRaises(AttributeError, lambda: f.foo)
        self.assertRaises(KeyError, lambda: f['foo'])


if __name__ == '__main__':
    unittest.main()
