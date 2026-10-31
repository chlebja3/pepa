"""Offline, evidence-based checks of link hostnames. Never visit a destination.

Only hostnames cross the extension bridge: paths, queries, fragments and URL
passwords are deliberately excluded. A warning is evidence to verify, not a
verdict that the destination is fraudulent.
"""
from datetime import date,datetime
from functools import lru_cache
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from page_signals import BRANDS,trusted

COI_SOURCE='https://coi.gov.cz/pro-spotrebitele/rizikove-e-shopy/'
COI_LICENSE='https://coi.gov.cz/pro-spotrebitele/otevrena-data/licence-otevrenych-dat/'
CONFUSABLES=str.maketrans({'а':'a','е':'e','о':'o','р':'p','с':'c','у':'y','х':'x','і':'i','ј':'j','ѕ':'s','к':'k','Ь':'b'})

def hostname(value,allow_empty=False):
    if value=='' and allow_empty:return ''
    if not isinstance(value,str) or not 1<=len(value)<=253 or any(c in value for c in '/@?#\\: \t\r\n'):
        # IPv6 literals are allowed, but never mistaken for a bank hostname.
        if isinstance(value,str) and value.startswith('[') and value.endswith(']'):
            try:return str(ipaddress.IPv6Address(value[1:-1]))
            except ValueError:pass
        raise ValueError('Expected hostname only')
    value=value.lower().rstrip('.')
    try:value=value.encode('idna').decode('ascii')
    except UnicodeError:raise ValueError('Invalid IDN')
    if len(value)>253:raise ValueError('Hostname too long')
    if not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*',value):raise ValueError('Invalid hostname')
    if any(len(label)>63 or label.startswith('-') or label.endswith('-') for label in value.split('.')):raise ValueError('Invalid hostname label')
    return value

def result(category,title,message,**extra):
    return {'status':'warning','category':category,'source':'local_link_check','title':title,'message':message,
            'advice':'Na odkaz zatím neklikejte. Službu otevřete samostatně ze své záložky nebo oficiální aplikace a adresu ověřte. Toto upozornění není důkaz podvodu.',**extra}

class LinkChecker:
    def __init__(self,snapshot=None,today=None):
        self.fixed_today=today;self.today=today or date.today();self.listed={};self.list_status='unavailable';self.retrieved=None
        if snapshot is None:
            path=Path(__file__).parent/'data/sources/coi-risky-sites-snapshot.json'
            if path.exists():snapshot=json.loads(path.read_text())
        if snapshot:
            self.retrieved=snapshot['retrieved_at'][:10]
            age=(self.today-date.fromisoformat(self.retrieved)).days
            self.list_status='fresh' if 0<=age<=30 else 'stale'
            for row in snapshot['records']:
                try:
                    parsed=urlsplit(row['url'] if '://' in row['url'] else 'https://'+row['url'])
                    # Host-only matching must not broaden a path-specific listing.
                    if parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username:continue
                    host=hostname(parsed.hostname or '').removeprefix('www.')
                    self.listed[host]=row['reason']
                except ValueError:continue
    def analyze(self,link):
        if not isinstance(link,dict) or set(link)!={'hostname','display_hostname','userinfo_hostname'}:raise ValueError('Invalid link metadata')
        host=hostname(link['hostname']);shown=hostname(link['display_hostname'],True);userinfo=hostname(link['userinfo_hostname'],True)
        for brand in BRANDS:
            domains=brand['domains']
            if trusted(host,domains):continue
            for domain in domains:
                if host.startswith(domain+'.') or ('.'+domain+'.') in host:
                    return result('bank_domain_in_host','Adresa banky je součástí cizí domény',f'Odkaz míří na {host}. Řetězec {domain} uvnitř adresy z něj nedělá doménu banky.')
            if shown and trusted(shown,domains):
                return result('bank_link_mismatch','Odkaz vede jinam, než ukazuje',f'Zobrazená adresa {shown} patří mezi známé domény banky, ale skutečný cíl je {host}. Může jít i o přesměrování; nejprve jej ověřte.')
            if userinfo and trusted(userinfo,domains):
                return result('bank_userinfo','Adresa banky je před znakem @',f'Skutečný cíl je {host}. Údaj {userinfo} před znakem @ není cílová doména banky.')
            if 'xn--' in host:
                try:decoded=host.encode('ascii').decode('idna').lower()
                except UnicodeError:decoded=host
                skeleton=decoded.translate(CONFUSABLES)
                if skeleton!=decoded and trusted(skeleton,domains):
                    return result('bank_confusable','Podobná písmena v adrese banky',f'Cíl {host} obsahuje znaky podobné známé adrese banky. Jde však o jinou doménu.')
        if self.list_status=='fresh':
            # Exact domain boundary; a listed shop's name inside another domain
            # is not a match. More-specific listings are checked first.
            parts=host.split('.')
            for i in range(len(parts)-1):
                key='.'.join(parts[i:]).removeprefix('www.')
                if key in self.listed:
                    return result('coi_risky_shop','Obchod je v uloženém seznamu rizikových e-shopů',
                        f'Česká obchodní inspekce uváděla {key} v seznamu staženém {self.retrieved}. Důvod: {self.listed[key]}',
                        source_url=COI_SOURCE,license_url=COI_LICENSE,snapshot_date=self.retrieved)
        return {'status':'no_signal','source':'local_link_check'}
    def batch(self,body):
        if self.retrieved:
            age=((self.fixed_today or date.today())-date.fromisoformat(self.retrieved)).days
            self.list_status='fresh' if 0<=age<=30 else 'stale'
        if not isinstance(body,dict) or set(body)!={'links'} or not isinstance(body['links'],list) or not 1<=len(body['links'])<=30:raise ValueError('Invalid link batch')
        results=[]
        for link in body['links']:
            if not isinstance(link,dict) or set(link)!={'hostname','display_hostname','userinfo_hostname'}:raise ValueError('Invalid link metadata')
            try:results.append(self.analyze(link))
            except ValueError:results.append({'status':'skipped','source':'local_link_check','reason':'Název domény nelze touto kontrolou zpracovat.'})
        return {'results':results,
                'list_status':self.list_status,'snapshot_date':self.retrieved,
                'limits':'Hostnames only; no redirect following, URL reputation lookup or safety certification.'}

@lru_cache(maxsize=1)
def checker(version):return LinkChecker()

def analyze_links(body):
    path=Path(__file__).parent/'data/sources/coi-risky-sites-snapshot.json'
    version=path.stat().st_mtime_ns if path.exists() else None
    return checker(version).batch(body)
