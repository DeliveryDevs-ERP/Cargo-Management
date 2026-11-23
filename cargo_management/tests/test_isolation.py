"""Prove disposable writers reject unsafe destinations before SQL or file access."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from cargo_management.tests import isolated_fixtures as fixtures


class TestDisposableIsolation(unittest.TestCase):
    def context(self,**changes):
        run='0123456789abcdef'
        values=dict(site='cargo-publication-'+run+'.localhost',db='cargo_publication_'+run,
                    marker=run,connected='cargo_publication_'+run,crypto=False,mute=True)
        values.update(changes)
        return SimpleNamespace(local=SimpleNamespace(site=values['site']),
            conf=dict(cargo_publication_test_run=values['marker'],db_name=values['db'],
                      cargo_crypto_enabled=values['crypto'],mute_emails=values['mute']),
            db=SimpleNamespace(sql=Mock(return_value=[(values['connected'],)])))

    def test_primary_alias_and_unknown_sites_fail_before_sql(self):
        for site in ('erp16.local','cargo.localhost','127.0.0.1','cargo-publication-unknown.localhost'):
            fake=self.context(site=site)
            with self.subTest(site=site),patch.object(fixtures,'frappe',fake):
                with self.assertRaises(RuntimeError):fixtures.require_disposable()
                fake.db.sql.assert_not_called()

    def test_missing_marker_and_wrong_database_fail_before_sql(self):
        for changes in ({'marker':''},{'marker':'invalid'},{'db':'_primary'}):
            fake=self.context(**changes)
            with self.subTest(changes=changes),patch.object(fixtures,'frappe',fake):
                with self.assertRaises(RuntimeError):fixtures.require_disposable()
                fake.db.sql.assert_not_called()

    def test_connected_database_must_match_configuration(self):
        with patch.object(fixtures,'frappe',self.context(connected='_primary')):
            with self.assertRaises(RuntimeError):fixtures.require_disposable()

    def test_external_effect_opt_ins_are_rejected(self):
        for changes in ({'crypto':True},{'mute':False}):
            with self.subTest(changes=changes),patch.object(fixtures,'frappe',self.context(**changes)):
                with self.assertRaises(RuntimeError):fixtures.require_disposable()

    def test_owned_disposable_pair_is_accepted(self):
        with patch.object(fixtures,'frappe',self.context()):
            self.assertEqual(fixtures.require_disposable(),'0123456789abcdef')
