# Copyright 2014 varnishapi authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

import json
import os
import unittest

from mock import patch
from collections import namedtuple

from varnishapi import api


class DatabaseTest(object):

    @classmethod
    def setUpClass(cls):
        os.environ["DB_PATH"] = ":memory:"
        reload(api)
        mydir = os.path.dirname(__file__)
        sql_path = os.path.realpath(os.path.join(mydir, "..",
                                                 "database.sql"))
        f = open(sql_path)
        sql = f.read().replace("\n", "")
        c = api.conn.cursor()
        c.execute(sql)

    @classmethod
    def tearDownClass(cls):
        c = api.conn.cursor()
        c.execute("drop table instance_app;")
        api.conn.close()


class TestHelper(object):

    def fake_reservation(self):
        Reservation = namedtuple("Reservation", ["instances"])
        Instance = namedtuple("Instance", ["id", "private_ip_address", "dns_name"])
        return Reservation(instances=[Instance(id="i-1",
                                               private_ip_address="192.169.56.101",
                                               dns_name="fakeinstance.amazonaws.com",
                                               )])


class EC2ConnectTestCase(unittest.TestCase):

    def setUp(self):
        api.access_key = "aws_access_key"
        api.secret_key = "aws_secret_key"

    @patch("boto.ec2.EC2Connection")
    def test_ec2_connection_http(self, ec2_mock):
        api.endpoint = "http://amazonaws.com"
        ec2_mock.return_value = "connection to ec2"
        result = api._ec2_connection()
        self.assertEqual("connection to ec2", result)
        ec2_mock.assert_called_with(aws_access_key_id=api.access_key,
                                    aws_secret_access_key=api.secret_key,
                                    host="amazonaws.com",
                                    port=80,
                                    path="/",
                                    is_secure=False)

    @patch("boto.ec2.EC2Connection")
    def test_ec2_connection_https(self, ec2_mock):
        api.endpoint = "https://amazonaws.com"
        ec2_mock.return_value = "connection to ec2"
        result = api._ec2_connection()
        self.assertEqual("connection to ec2", result)
        ec2_mock.assert_called_with(aws_access_key_id=api.access_key,
                                    aws_secret_access_key=api.secret_key,
                                    host="amazonaws.com",
                                    port=443,
                                    path="/",
                                    is_secure=True)

    @patch("boto.ec2.EC2Connection")
    def test_ec2_connection_http_custom_port(self, ec2_mock):
        api.endpoint = "http://amazonaws.com:8080"
        ec2_mock.return_value = "connection to ec2"
        result = api._ec2_connection()
        self.assertEqual("connection to ec2", result)
        ec2_mock.assert_called_with(aws_access_key_id=api.access_key,
                                    aws_secret_access_key=api.secret_key,
                                    host="amazonaws.com",
                                    port=8080,
                                    path="/",
                                    is_secure=False)

    @patch("boto.ec2.EC2Connection")
    def test_ec2_connection_https_custom_port(self, ec2_mock):
        api.endpoint = "https://amazonaws.com:8080"
        ec2_mock.return_value = "connection to ec2"
        result = api._ec2_connection()
        self.assertEqual("connection to ec2", result)
        ec2_mock.assert_called_with(aws_access_key_id=api.access_key,
                                    aws_secret_access_key=api.secret_key,
                                    host="amazonaws.com",
                                    port=8080,
                                    path="/",
                                    is_secure=True)

    @patch("boto.ec2.EC2Connection")
    def test_ec2_connection_custom_path(self, ec2_mock):
        api.endpoint = "https://amazonaws.com:8080/something"
        ec2_mock.return_value = "connection to ec2"
        result = api._ec2_connection()
        self.assertEqual("connection to ec2", result)
        ec2_mock.assert_called_with(aws_access_key_id=api.access_key,
                                    aws_secret_access_key=api.secret_key,
                                    host="amazonaws.com",
                                    port=8080,
                                    path="/something",
                                    is_secure=True)


class CreateInstanceTestCase(DatabaseTest, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.api = api.api.test_client()
        cls.helper = TestHelper()
        os.environ["EC2_ACCESS_KEY"] = "access"
        os.environ["EC2_SECRET_KEY"] = "secret"
        os.environ["AMI_ID"] = "ami-123"
        os.environ["SUBNET_ID"] = "subnet-123"
        os.environ["KEY_PATH"] = "/tmp/testkey.pub"
        reload(api)
        DatabaseTest.setUpClass()
        f = file(os.environ["KEY_PATH"], "w+")
        f.write("testkey 123")
        f.close()

    def tearDown(self):
        c = api.conn.cursor()
        c.execute("delete from instance_app;")

    @classmethod
    def tearDownClass(cls):
        os.remove(os.environ["KEY_PATH"])
        del os.environ["EC2_ACCESS_KEY"]
        del os.environ["EC2_SECRET_KEY"]
        del os.environ["AMI_ID"]
        del os.environ["SUBNET_ID"]
        del os.environ["KEY_PATH"]
        DatabaseTest.tearDownClass()

    @patch("boto.ec2.EC2Connection")
    def test_create_instance_should_return_201(self, mock):
        resp = self.api.post("/resources", data={"name": "someapp"})
        self.assertEqual(resp.status_code, 201)

    @patch("boto.ec2.EC2Connection")
    def test_should_create_instance_on_ec2(self, mock):
        instance = mock.return_value
        r = self.helper.fake_reservation()
        instance.run_instances.return_value = r
        self.api.post("/resources", data={"name": "someapp"})
        self.assertTrue(instance.run_instances.called)

    @patch("boto.ec2.EC2Connection")
    def test_should_create_instance_on_ec2_using_subnet_and_ami(self, mock):
        instance = mock.return_value
        self.api.post("/resources", data={"name": "someapp"})
        f = open(api.key_path)
        key = f.read()
        f.close()
        user_data = """#cloud-config
ssh_authorized_keys: ['{0}']
""".format(key)
        instance.run_instances.assert_called_once_with(image_id=api.ami_id,
                                                       subnet_id=api.subnet_id,
                                                       user_data=user_data)

    @patch("boto.ec2.EC2Connection")
    def test_should_store_instance_id_app_and_dns_name_on_database(self, mock):
        instance = mock.return_value
        r = self.helper.fake_reservation()
        instance.run_instances.return_value = r
        self.api.post("/resources", data={"name": "someapp"})
        c = api.conn.cursor()
        c.execute("select * from instance_app;")
        result = c.fetchall()
        expected = [("i-1", "someapp", "fakeinstance.amazonaws.com")]
        self.assertListEqual(expected, result)

    @patch("boto.ec2.EC2Connection")
    @patch("syslog.syslog")
    def test_should_log_error_when_cannot_create_ec2_instance(self, log_mock, ec2_mock):
        instance = ec2_mock.return_value
        instance.run_instances.side_effect = Exception("BoOm!")
        resp = self.api.post("/resources", data={"name": "someapp"})
        self.assertEqual(500, resp.status_code)
        self.assertEqual("Caught error while creating service instance.", resp.data)
        self.assertEqual(4, log_mock.call_count)


class DeleteInstanceTestCase(DatabaseTest, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.api = api.api.test_client()
        os.environ["EC2_ACCESS_KEY"] = "access"
        os.environ["EC2_SECRET_KEY"] = "secret"
        reload(api)
        DatabaseTest.setUpClass()

    @classmethod
    def tearDownClass(cls):
        del os.environ["EC2_ACCESS_KEY"]
        del os.environ["EC2_SECRET_KEY"]
        DatabaseTest.tearDownClass()

    def tearDown(self):
        c = api.conn.cursor()
        c.execute("delete from instance_app;")

    @patch("boto.ec2.EC2Connection")
    @patch("varnishapi.api._get_instance_id")
    def test_should_get_and_be_success(self, mock, ec2_mock):
        mock.return_value = ["i-1"]
        r = self.api.delete("/resources/service_instance_name")
        self.assertEqual(200, r.status_code)

    @patch("boto.ec2.EC2Connection")
    def test_should_call_ec2_terminate_instances(self, mock):
        instance = mock.return_value
        instance.terminate_instances.return_value = ["i-1"]
        c = api.conn.cursor()
        c.execute("insert into instance_app values ('i-1', 'si_name', 'elb-dns.elb.amazon.com')")
        self.api.delete("/resources/si_name")
        instance.terminate_instances.assert_called_once_with(instance_ids=["i-1"])

    @patch("boto.ec2.EC2Connection")
    def test_should_remove_record_from_the_database(self, mock):
        c = api.conn.cursor()
        c.execute("insert into instance_app values ('i-1', 'si_name', 'elb-dns.elb.amazon.com')")
        self.api.delete("/resources/si_name")
        c.execute("select * from instance_app where app_name='si_name'")
        results = c.fetchall()
        self.assertListEqual([], results)


class BindTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.api = api.api.test_client()
        cls.helper = TestHelper()
        os.environ["EC2_ACCESS_KEY"] = "access"
        os.environ["EC2_SECRET_KEY"] = "secret"
        reload(api)

    @classmethod
    def tearDownClass(cls):
        del os.environ["EC2_ACCESS_KEY"]
        del os.environ["EC2_SECRET_KEY"]

    @patch("subprocess.call")
    @patch("boto.ec2.EC2Connection")
    @patch("varnishapi.api._get_instance_id")
    def test_should_get_instance_id_from_database(self, mock, ec2_mock, sp_mock):
        sp_mock.return_value = 0
        mock.return_value = "i-1"
        resp = self.api.post("/resources/si_name")
        self.assertEqual(201, resp.status_code)
        mock.assert_called_once_with(service_instance="si_name")

    @patch("subprocess.call")
    @patch("boto.ec2.EC2Connection")
    @patch("varnishapi.api._get_instance_id")
    def test_should_get_instance_ip_from_amazon(self, mock, ec2_mock, sp_mock):
        sp_mock.return_value = 0
        mock.return_value = "i-1"
        instance = ec2_mock.return_value
        instance.get_all_instances.return_value = [self.helper.fake_reservation()]
        self.api.post("/resources/si_name")
        instance.get_all_instances.assert_called_once_with(instance_ids=["i-1"])

    @patch("subprocess.call")
    @patch("boto.ec2.EC2Connection")
    @patch("varnishapi.api._get_instance_ip")
    @patch("varnishapi.api._get_instance_id")
    def test_should_ssh_into_service_instance_and_update_vcl_file_using_template(self,
                                                                                 mock,
                                                                                 ip_mock,
                                                                                 ec2_mock,
                                                                                 sp_mock):
        si_ip = "10.2.2.1"
        app_ip = "10.1.1.2"
        sp_mock.return_value = 0
        ip_mock.return_value = si_ip
        self.api.post("/resources/si_name", data={"app-host": app_ip})
        self.assertTrue(sp_mock.called)
        cmd = "sudo bash -c \"echo '{0}' > /etc/varnish/default.vcl && service varnish reload\""
        cmd = cmd.format(api.vcl_template.format(app_ip))
        expected = ["ssh", si_ip, "-l", "ubuntu", "-o", "StrictHostKeyChecking no", cmd]
        cmd_arg = sp_mock.call_args_list[0][0][0]
        self.assertEqual(expected, cmd_arg)


class UnbindTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.api = api.api.test_client()
        cls.helper = TestHelper()
        os.environ["EC2_ACCESS_KEY"] = "access"
        os.environ["EC2_SECRET_KEY"] = "secret"
        reload(api)

    @classmethod
    def tearDownClass(cls):
        del os.environ["EC2_ACCESS_KEY"]
        del os.environ["EC2_SECRET_KEY"]

    @patch("boto.ec2.EC2Connection")
    @patch("varnishapi.api._get_instance_id")
    @patch("varnishapi.api._clean_vcl_file")
    def test_unbind_should_get_instance_id(self, vcl_mock, mock, ec2_mock):
        resp = self.api.delete("/resources/si_name/hostname/10.1.1.2")
        self.assertEqual(200, resp.status_code)
        mock.assert_called_once_with(service_instance="si_name")

    @patch("boto.ec2.EC2Connection")
    @patch("varnishapi.api._get_instance_id")
    @patch("varnishapi.api._get_instance_ip")
    @patch("varnishapi.api._clean_vcl_file")
    def test_unbind_should_get_instance_ip(self, vcl_mock, mock, id_mock, ec2_mock):
        id_mock.return_value = "i-1"
        resp = self.api.delete("/resources/si_name/hostname/10.1.1.2")
        self.assertEqual(200, resp.status_code)
        mock.assert_called_once_with(instance_id="i-1")

    @patch("boto.ec2.EC2Connection")
    @patch("varnishapi.api._get_instance_id")
    @patch("varnishapi.api._get_instance_ip")
    @patch("subprocess.call")
    def test_should_clear_vcl_file(self, sp_mock, ip_mock, id_mock, ec2_mock):
        si_ip = "10.2.2.1"
        ip_mock.return_value = si_ip
        self.api.delete("/resources/si_name/hostname/10.1.1.2")
        sp_mock.return_value = 0
        self.assertTrue(sp_mock.called)
        cmd = "sudo bash -c \"echo '{0}' > /etc/varnish/default.vcl && service varnish reload\""
        cmd = cmd.format(api.vcl_template.format("localhost"))
        expected = ["ssh", si_ip, "-l", "ubuntu", cmd]
        cmd_arg = sp_mock.call_args_list[0][0][0]
        self.assertEqual(expected, cmd_arg)


class InfoTestCase(DatabaseTest, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.api = api.api.test_client()
        DatabaseTest.setUpClass()

    def test_should_return_dns_name_from_database(self):
        dns_name = "elb-dns.elb.amazon.com"
        c = api.conn.cursor()
        c.execute("insert into instance_app values (?, ?, ?)", ["i-1", "si_name", dns_name])
        resp = self.api.get("/resources/si_name")
        self.assertEqual(200, resp.status_code)
        expected = [{"label": "DNS Name", "value": dns_name}]
        self.assertListEqual(expected, json.loads(resp.data))


class HelpersTestcase(unittest.TestCase):

    def test_get_database_name_should_return_absolute_path_to_it(self):
        del os.environ["DB_PATH"]
        db_name = api._get_database_name()
        mydir = os.path.dirname(__file__)
        expected = os.path.realpath(os.path.join(mydir, "..", "varnishapi",
                                                 api.default_db_name))
        self.assertEqual(expected, db_name)

    def test_get_database_name_should_use_DB_PATH_env_var_when_its_set(self):
        os.environ["DB_PATH"] = ":memory:"
        reload(api)
        got = api._get_database_name()
        self.assertEqual(os.environ["DB_PATH"], got)
        del os.environ["DB_PATH"]