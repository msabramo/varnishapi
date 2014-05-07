# Copyright 2014 varnishapi authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

import unittest

import freezegun
import pymongo

from feaas import storage


class InstanceTestCase(unittest.TestCase):

    def test_init_with_units(self):
        units = [storage.Unit(id="i-0800"), storage.Unit(id="i-0801")]
        instance = storage.Instance(name="something", units=units)
        for unit in units:
            self.assertEqual(instance, unit.instance)

    def test_to_dict(self):
        instance = storage.Instance(name="myinstance")
        expected = {"name": "myinstance"}
        self.assertEqual(expected, instance.to_dict())

    def test_add_unit(self):
        unit1 = storage.Unit(dns_name="instance1.cloud.tsuru.io", id="i-0800")
        unit2 = storage.Unit(dns_name="instance2.cloud.tsuru.io", id="i-0801")
        instance = storage.Instance()
        instance.add_unit(unit1)
        instance.add_unit(unit2)
        self.assertEqual([unit1, unit2], instance.units)

    def test_remove_unit(self):
        unit1 = storage.Unit(dns_name="instance1.cloud.tsuru.io", id="i-0800")
        unit2 = storage.Unit(dns_name="instance2.cloud.tsuru.io", id="i-0801")
        instance = storage.Instance()
        instance.add_unit(unit1)
        instance.add_unit(unit2)
        self.assertEqual([unit1, unit2], instance.units)
        instance.remove_unit(unit1)
        self.assertEqual([unit2], instance.units)


class UnitTestCase(unittest.TestCase):

    def test_to_dict(self):
        instance = storage.Instance(name="myinstance")
        unit = storage.Unit(id="i-0800", dns_name="instance.cloud.tsuru.io",
                            secret="abc123", state="started", instance=instance)
        expected = {"id": "i-0800", "dns_name": "instance.cloud.tsuru.io",
                    "secret": "abc123", "state": "started",
                    "instance_name": "myinstance"}
        self.assertEqual(expected, unit.to_dict())


class BindTestCase(unittest.TestCase):

    def test_to_dict(self):
        instance = storage.Instance(name="myinstance")
        bind = storage.Bind("wat.g1.cloud.tsuru.io", instance)
        expected = {"app_host": "wat.g1.cloud.tsuru.io",
                    "instance_name": "myinstance",
                    "created_at": bind.created_at}
        self.assertEqual(expected, bind.to_dict())


class MongoDBStorageTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = pymongo.MongoClient('localhost', 27017)

    @classmethod
    def tearDownClass(cls):
        cls.client.drop_database("feaas_test")

    def setUp(self):
        self.storage = storage.MongoDBStorage(dbname="feaas_test")

    def test_store_instance(self):
        instance = storage.Instance(name="secret")
        self.storage.store_instance(instance)
        self.addCleanup(self.client.feaas_test.instances.remove, {"name": "secret"})
        instance = self.client.feaas_test.instances.find_one({"name": "secret"})
        expected = {"name": "secret", "_id": instance["_id"]}
        self.assertEqual(expected, instance)

    def test_store_instance_with_units(self):
        units = [storage.Unit(dns_name="instance.cloud.tsuru.io", id="i-0800")]
        instance = storage.Instance(name="secret", units=units)
        self.storage.store_instance(instance)
        self.addCleanup(self.client.feaas_test.instances.remove, {"name": "secret"})
        self.addCleanup(self.client.feaas_test.units.remove, {"instance_name": "secret"})
        instance = self.client.feaas_test.instances.find_one({"name": "secret"})
        expected = {"name": "secret", "_id": instance["_id"]}
        self.assertEqual(expected, instance)
        unit = self.client.feaas_test.units.find_one({"id": "i-0800",
                                                      "instance_name": "secret"})
        expected = units[0].to_dict()
        expected["_id"] = unit["_id"]
        self.assertEqual(expected, unit)

    def test_store_instance_update_with_units(self):
        units = [storage.Unit(dns_name="instance1.cloud.tsuru.io", id="i-0800"),
                 storage.Unit(dns_name="instance2.cloud.tsuru.io", id="i-0801"),
                 storage.Unit(dns_name="instance3.cloud.tsuru.io", id="i-0802")]
        instance = storage.Instance(name="secret", units=units)
        self.storage.store_instance(instance)
        self.addCleanup(self.client.feaas_test.instances.remove, {"name": "secret"})
        self.addCleanup(self.client.feaas_test.units.remove, {"instance_name": "secret"})
        self.assert_units(units, "secret")
        new_units = units[1:]
        instance.units = new_units
        self.storage.store_instance(instance)
        self.assert_units(new_units, "secret")

    def test_retrieve_instance(self):
        expected = storage.Instance(name="what")
        self.storage.store_instance(expected)
        got = self.storage.retrieve_instance("what")
        self.assertEqual(expected.to_dict(), got.to_dict())

    def test_retrieve_instance_not_found(self):
        with self.assertRaises(storage.InstanceNotFoundError):
            self.storage.retrieve_instance("secret")

    def test_remove_instance(self):
        instance = storage.Instance(name="years")
        self.storage.store_instance(instance)
        self.storage.remove_instance(instance.name)
        self.assertIsNone(self.client.feaas_test.instances.find_one({"name": instance.name}))

    @freezegun.freeze_time("2014-02-16 12:00:01")
    def test_store_bind(self):
        instance = storage.Instance(name="years")
        bind = storage.Bind(app_host="something.where.com", instance=instance)
        self.storage.store_bind(bind)
        self.addCleanup(self.client.feaas_test.binds.remove,
                        {"instance_name": "years"})
        got = self.client.feaas_test.binds.find_one({"instance_name": "years"})
        expected = bind.to_dict()
        expected["_id"] = got["_id"]
        expected["created_at"] = got["created_at"]
        self.assertEqual(expected, got)

    @freezegun.freeze_time("2014-02-16 12:00:01")
    def test_retrieve_binds(self):
        instance = storage.Instance(name="years")
        bind1 = storage.Bind(app_host="something.where.com", instance=instance)
        self.storage.store_bind(bind1)
        bind2 = storage.Bind(app_host="belong.where.com", instance=instance)
        self.storage.store_bind(bind2)
        self.addCleanup(self.client.feaas_test.binds.remove,
                        {"instance_name": "years"})
        binds = self.storage.retrieve_binds("years")
        binds = [b.to_dict() for b in binds]
        self.assertEqual([bind1.to_dict(), bind2.to_dict()], binds)

    def test_remove_bind(self):
        instance = storage.Instance(name="years")
        bind = storage.Bind(app_host="something.where.com", instance=instance)
        self.storage.store_bind(bind)
        self.addCleanup(self.client.feaas_test.binds.remove,
                        {"instance_name": "years"})
        self.storage.remove_bind(bind)
        self.assertEqual([], self.storage.retrieve_binds("years"))

    def test_lock_vcl_writer(self):
        self.storage.lock_vcl_writer()
        self.addCleanup(self.storage.unlock_vcl_writer)
        lock = self.client.feaas_test.vcl_lock.find_one()
        self.assertEqual("1", lock["_id"])
        self.assertEqual(1, lock["state"])
        self.storage.unlock_vcl_writer()
        self.storage.lock_vcl_writer()
        lock = self.client.feaas_test.vcl_lock.find_one()
        self.assertEqual("1", lock["_id"])
        self.assertEqual(1, lock["state"])

    def test_unlock_vcl_writer(self):
        self.storage.lock_vcl_writer()
        self.storage.unlock_vcl_writer()
        lock = self.client.feaas_test.vcl_lock.find_one()
        self.assertEqual("1", lock["_id"])
        self.assertEqual(0, lock["state"])

    def test_unlock_vcl_writer_double(self):
        self.storage.lock_vcl_writer()
        self.storage.unlock_vcl_writer()
        with self.assertRaises(storage.DoubleUnlockError):
            self.storage.unlock_vcl_writer()

    def assert_units(self, expected_units, instance_name):
        cursor = self.client.feaas_test.units.find({"instance_name": instance_name})
        units = []
        expected = [u.to_dict() for u in expected_units]
        for i, unit in enumerate(cursor):
            expected[i]["_id"] = unit["_id"]
            units.append(unit)
        self.assertEqual(expected, units)
