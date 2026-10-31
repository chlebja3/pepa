from pathlib import Path
import sys
import unittest
# the modules sit in helper/ in the release and at the top of the development tree
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'helper'), str(ROOT)]
from page_signals import analyze_page

class PageSignalsTests(unittest.TestCase):
    def page(self, host='login.kb.cz', **changes):
        page=dict(hostname=host, scheme='https:', brand_text='Komerční banka',
                  forms=[dict(password=True, action_host=host, action_scheme='https:')])
        page.update(changes)
        return page

    def test_official_bank_login_has_no_signal(self):
        self.assertEqual(analyze_page(self.page())['status'], 'no_signal')

    def test_deceptive_domain_boundaries(self):
        for host in ['kb.cz.evil.example', 'fakekb.cz', 'bank.example']:
            with self.subTest(host=host):
                self.assertEqual(analyze_page(self.page(host))['category'], 'bank_impersonation')

    def test_official_page_sending_password_elsewhere(self):
        page=self.page(forms=[dict(password=True, action_host='evil.example', action_scheme='https:')])
        self.assertEqual(analyze_page(page)['category'], 'bank_impersonation')

    def test_bank_article_is_not_login(self):
        self.assertEqual(analyze_page(self.page('news.example', forms=[]))['status'], 'no_signal')

    def test_http_password_warning(self):
        self.assertEqual(analyze_page(self.page(scheme='http:'))['category'], 'insecure_login')

    def test_george_person_name_is_not_a_bank_claim(self):
        self.assertEqual(analyze_page(self.page('literature.example',brand_text='George Orwell — přihlášení do čtenářského klubu'))['status'],'no_signal')

    def test_george_banking_context_identifies_bank(self):
        self.assertEqual(analyze_page(self.page('unknown.example',brand_text='George internetové bankovnictví'))['category'],'bank_impersonation')

    def test_password_values_rejected(self):
        with self.assertRaises(ValueError):
            analyze_page(self.page(forms=[dict(password=True, value='secret')]))

    def test_unrecognized_brand_is_not_automatically_fraud(self):
        self.assertEqual(analyze_page(self.page('shop.example', brand_text='My shop'))['status'], 'no_signal')

if __name__ == '__main__':
    unittest.main()
