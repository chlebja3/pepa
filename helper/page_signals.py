"""Deterministic page evidence, separate from the text model. No reputation requests.

Known login domains verified against the institutions' public pages; this limited
list is not a general allow-list or a guarantee that an official site is safe.
"""
import re
import unicodedata

BRANDS=[
 {'name':'Česká spořitelna / George','terms':['ceska sporitelna'], 'ambiguous_terms':['george'], 'context_terms':['bankovnictvi','bankovni','sporitelna'],'domains':['csas.cz','servis24.cz'], 'source':'https://www.csas.cz/cs/zpravy-z-banky/2022/07/15/pozor-na-podvodne-odkazy-ve-vyhledavacich'},
 {'name':'Komerční banka','terms':['komercni banka','mojebanka','kb+'],'domains':['kb.cz','mojebanka.cz'],'source':'https://www.kb.cz/cs/nase-aplikace/mojebanka'},
]
def normalize(text):return ''.join(c for c in unicodedata.normalize('NFKD',text.lower()) if not unicodedata.combining(c))
def trusted(host,domains):return any(host==d or host.endswith('.'+d) for d in domains)
def analyze_page(page):
    if not isinstance(page,dict) or set(page)-{'hostname','scheme','brand_text','forms'}:raise ValueError('Invalid page metadata')
    host=page.get('hostname','')
    if not isinstance(host,str):raise ValueError('Invalid hostname')
    host=host.lower().rstrip('.')
    if len(host)>253 or not re.fullmatch(r'[a-z0-9.-]+',host):raise ValueError('Invalid hostname')
    brand_text=page.get('brand_text','');forms=page.get('forms',[])
    if not isinstance(brand_text,str) or len(brand_text)>1200 or not isinstance(forms,list) or len(forms)>12:raise ValueError('Invalid page metadata')
    for f in forms:
        if not isinstance(f,dict) or set(f)-{'password','action_host','action_scheme'} or not isinstance(f.get('password'),bool):raise ValueError('Invalid form metadata')
        if not isinstance(f.get('action_host',''),str) or len(f.get('action_host',''))>253:raise ValueError('Invalid action host')
    password_forms=[f for f in forms if f['password']]
    if not password_forms:return {'status':'no_signal','source':'page_structure'}
    if page.get('scheme')=='http:' or any(f.get('action_scheme')=='http:' for f in password_forms):
        return {'status':'warning','category':'insecure_login','source':'page_structure','title':'Heslo na nešifrované stránce',
                'message':f'Na doméně {host} je pole pro heslo, ale stránka nebo cíl formuláře používá HTTP bez šifrování.',
                'advice':'Heslo zatím nezadávejte. Otevřete službu přes její známou adresu s HTTPS. Samotné HTTPS však pravost nepotvrzuje.'}
    text=normalize(brand_text)
    for brand in BRANDS:
        def mentioned(term):return re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text) is not None
        identified=any(mentioned(term) for term in brand['terms'])
        identified=identified or (any(mentioned(term) for term in brand.get('ambiguous_terms',[])) and any(mentioned(term) for term in brand.get('context_terms',[])))
        if not identified:continue
        bad_destination=any(f.get('action_host') and not trusted(f['action_host'].lower().rstrip('.'),brand['domains']) for f in password_forms)
        if not trusted(host,brand['domains']) or bad_destination:
            return {'status':'warning','category':'bank_impersonation','source':'page_structure','title':f'Ověřte přihlášení — {brand["name"]}',
                    'message':f'Stránka zmiňuje {brand["name"]} a žádá heslo. Doména {host} nebo cíl formuláře neodpovídá známým přihlašovacím doménám této banky.',
                    'advice':'Heslo nezadávejte, dokud adresu neověříte. Banku otevřete ze své záložky nebo její oficiální aplikace. Jde o nesoulad stránky, nikoli potvrzený podvod.'}
    return {'status':'no_signal','source':'page_structure'}
