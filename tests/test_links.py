from datetime import date
from pathlib import Path
import sys
import unittest
# the modules sit in helper/ in the release and at the top of the development tree
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'helper'), str(ROOT)]
from link_signals import LinkChecker,hostname

SNAPSHOT={'retrieved_at':'2026-10-27T09:00:00Z','records':[{'url':'risky.example','reason':'Provozovatel není uveden.'},{'url':'shared.example/shop-bad','reason':'Path-specific listing.'}]}
class LinkTests(unittest.TestCase):
    def setUp(self):self.checker=LinkChecker(SNAPSHOT,date(2026,10,27))
    def link(self,host,shown='',userinfo=''):
        return {'hostname':host,'display_hostname':shown,'userinfo_hostname':userinfo}
    def test_bank_suffix_deception(self):
        for host in ['csas.cz.attacker.invalid','www.kb.cz.evil.example','login.mojebanka.cz.example.invalid']:
            with self.subTest(host=host):self.assertEqual(self.checker.analyze(self.link(host))['category'],'bank_domain_in_host')
    def test_displayed_bank_url_mismatch(self):
        self.assertEqual(self.checker.analyze(self.link('unknown.example','www.csas.cz'))['category'],'bank_link_mismatch')
    def test_bank_identity_in_userinfo(self):
        self.assertEqual(self.checker.analyze(self.link('unknown.example',userinfo='kb.cz'))['category'],'bank_userinfo')
    def test_bank_confusable(self):
        self.assertEqual(self.checker.analyze(self.link('csаs.cz'.encode('idna').decode()))['category'],'bank_confusable') # Cyrillic a
    def test_official_bank_aliases_are_not_mismatches(self):
        for host,shown in [('login.csas.cz','csas.cz'),('servis24.cz','csas.cz'),('mojebanka.cz','kb.cz')]:
            with self.subTest(host=host):self.assertEqual(self.checker.analyze(self.link(host,shown))['status'],'no_signal')
    def test_unfamiliar_idn_ip_shortener_and_tracking_are_not_fraud_by_themselves(self):
        for host in ['xn--bcher-kva.example','192.0.2.1','[2001:db8::1]','short.example','click.newsletter.example','bank.example','notcsas.cz']:
            with self.subTest(host=host):self.assertEqual(self.checker.analyze(self.link(host))['status'],'no_signal')
    def test_coi_boundary_and_attribution(self):
        result=self.checker.analyze(self.link('shop.risky.example'))
        self.assertEqual(result['category'],'coi_risky_shop');self.assertIn('Česká obchodní inspekce',result['message'])
        self.assertIn('2026-10-27',result['message']);self.assertIn('Provozovatel není uveden.',result['message'])
        for host in ['notrisky.example','risky.example.evil.invalid','shared.example']:
            self.assertEqual(self.checker.analyze(self.link(host))['status'],'no_signal')
    def test_stale_list_not_used_as_current_evidence(self):
        checker=LinkChecker(SNAPSHOT,date(2026,12,1))
        response=checker.batch({'links':[self.link('risky.example')]})
        self.assertEqual(response['list_status'],'stale');self.assertEqual(response['results'][0]['status'],'no_signal')
        self.assertEqual(checker.analyze(self.link('csas.cz.evil.example'))['status'],'warning')
    def test_raw_urls_and_secrets_rejected(self):
        for value in ['https://kb.cz/?token=secret','user:password@kb.cz','kb.cz/path','bad host','-bad.example']:
            with self.subTest(value=value), self.assertRaises(ValueError):hostname(value)
        with self.assertRaises(ValueError):self.checker.batch({'links':[dict(self.link('example.org'),url='private')]})
    def test_batch_size_and_schema(self):
        for body in [{'links':[]},{'links':[self.link('example.org')]*31},{'links':[],'token':'secret'}]:
            with self.assertRaises(ValueError):self.checker.batch(body)
    def test_one_invalid_hostname_cannot_disable_the_batch(self):
        result=self.checker.batch({'links':[self.link('host_with_underscore.example'),self.link('csas.cz.evil.invalid')]})
        self.assertEqual([r['status'] for r in result['results']],['skipped','warning'])

    def test_no_network_needed(self):
        from unittest.mock import patch
        with patch('socket.socket.connect',side_effect=AssertionError('No connections allowed')):
            self.assertEqual(self.checker.analyze(self.link('csas.cz.evil.example'))['status'],'warning')

if __name__=='__main__':unittest.main()
