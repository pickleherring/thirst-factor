"""Quantify the horniness of ships.

Counts total fics and number of explicit fics for 1176 possible pairings, including characters with themselves.
To stay within AO3's rate limit for automated access, there is a 5-second pause between counts.
So this script will take quite a long time to run.

Character list is read from 'names.txt'.

Results are saved to 'ships.csv' with columns:
    A: character name
    B: character name
    ship: slash-format ship name
    fics: number of fics found
    explicit: number of explicit fics found
    p: proportion of fics that are explicit
"""

import itertools
import os
import time

import bs4
import pandas
import regex
import requests


username = os.environ.get('AO3_USERNAME')
password = os.environ.get('AO3_PASSWORD')

# NOTE: Set a very conservative sleep period to avoid AO3's rate limiting.
sleep_period = 5
backoff_factor = 60

login_url = 'https://archiveofourown.org/users/login'
search_url = 'https://archiveofourown.org/works/search'
search_field_ship = 'work_search[query]'
search_field_rating = 'work_search[rating_ids]'
explicit_rating_id = 13

parser = 'lxml'

work_count_pattern = regex.compile('[0-9,]+')

# NOTE: AO3's canonical tag for Vander now places him in League fandom, not Arcane
champions = [
    'Caitlyn',
    'Ekko',
    'Heimerdinger',
    'Jayce',
    'Jinx',
    'Singed',
    'Vander',
    'Vi',
    'Viktor',
]

special_case_names = [
    'Brothel Girl',
    'Local Cuisine Guy',
]


class LoginError(Exception):
    pass


class RateLimitedError(Exception):
    pass


def wrangle_fandom_tag(name):
    """Determine the appropriate fandom tag for an Arcane character.
    
    fandom for league champions is 'League of Legends'
    fandom for non-champion Arcane characters is 'Arcane: League of Legends'
    """

    if name in champions:
        return ' (League of Legends)'
    else:
        return ' (Arcane: League of Legends)'


def reverse_names(name):
    """Helper function for reversing name order.
    
    i.e. switches first name and last name
    """

    if name in special_case_names:
        return name
    else:
        names = name.split()
        names.reverse()
        return ' '.join(names)


def is_multiple_name(name):
    """Helper function for counting names.
    
    i.e. does character have first name and family name?
    """

    if name in special_case_names:
        return False
    else:
        return len(name.split()) > 1


def wrangle_relationship_tag(name1, name2):
    """Determine the canonical relationship tag for a pairing.

    Follows AO3 wrangling guidelines for relationship and name tags:
    https://archiveofourown.org/wrangling_guidelines/7
    https://archiveofourown.org/wrangling_guidelines/8

    names in alphabetical order by last name, separated by slash
    characters are from same fandom and at least one is double-name -> no fandom disambiguation
    characters are from same fandom and both are single-name -> overall fandom disambiguation at end of tag
    characters are from separate fandoms -> fandom disambiguation for any single-name characters
    """

    name1, name2 = sorted((name1, name2), key=reverse_names)
    fandom1 = wrangle_fandom_tag(name1)
    fandom2 = wrangle_fandom_tag(name2)

    if fandom1 == fandom2:
        fandom1 = ''
        if is_multiple_name(name1) or is_multiple_name(name2):
            fandom2 = ''
    else:
        if is_multiple_name(name1):
            fandom1 = ''
        if is_multiple_name(name2):
            fandom2 = ''
    
    return f'{name1}{fandom1}/{name2}{fandom2}'


def login(session, username, password):
    """Log in to AO3.
    """

    response = session.get(login_url)
    soup = bs4.BeautifulSoup(response.text, features=parser)
    authenticity_token = soup.find('input', attrs={'name': 'authenticity_token'})['value']

    params = {
        'user[login]': username,
        'user[password]': password,
        'authenticity_token': authenticity_token
    }

    response = session.post(login_url, params=params, allow_redirects=False)
    
    if response.status_code != 302:
        raise LoginError('invalid username or password')

    return session


def get_work_count(session, params):
    """Get number of works for a search.

    Just reads the result count, doesn't check each work.
    """

    response = session.get(search_url, params=params)

    if response.status_code == 429:
        raise RateLimitedError(f'rate limited with sleep period {sleep_period}, try increasing')

    soup = bs4.BeautifulSoup(response.text, features=parser)
    main_div = soup.find('div', attrs={'id': 'main'})

    if main_div is None:
        print('\n[DEBUG] invalid response text but no rate limit warning in response\n')
        print(response.status_code)
        print(response.text)
        raise RateLimitedError()

    header = main_div.find('h3', attrs={'class': 'heading'})

    if header:
        work_count = work_count_pattern.match(header.get_text()).group(0)
        work_count = int(work_count.replace(',', ''))
    else:
        work_count = 0

    return work_count


def get_work_counts_for_ship(session, name1, name2):
    """Get number of works and explicit works for a relationship.

    Searches by canonical relationship tag (see wrangle_relationship_tag).
    """

    relationship_tag = wrangle_relationship_tag(name1, name2)
    params = {search_field_ship: f'"{relationship_tag}"'}
    total = get_work_count(session, params=params)

    if total:
        time.sleep(sleep_period)
        params[search_field_rating] = explicit_rating_id
        explicit = get_work_count(session, params=params)
    else:
        explicit = 0

    return total, explicit


if __name__ == '__main__':

    with open('names.txt') as f:
        names = f.read().splitlines()

    ships = pandas.DataFrame(
        itertools.combinations_with_replacement(names, 2),
        columns=['A', 'B']
    )

    ships['ship'] = ships['A'].str.cat(ships['B'], sep='/')

    n_pairs = ships.shape[0]
    totals = []
    n_explicit = []
    started = False

    session = requests.Session()
    session.mount(
        'https://',
        requests.adapters.HTTPAdapter(
            max_retries=requests.adapters.Retry(
                status=7,
                status_forcelist=[429],
                backoff_factor=backoff_factor
            )
        )
    )

    if username and password:
        session = login(session, username, password)
        print(f'logged in as {username}')
    else:
        print('anonymous user session, not all fics will be visible')
    
    output_filename = 'ships.csv'

    for a, b in zip(ships['A'], ships['B']):

        if started:
            time.sleep(sleep_period)
        else:
            started = True

        try:
            total, explicit = get_work_counts_for_ship(session, a, b)
            totals.append(total)
            n_explicit.append(explicit)
            print(f'[{len(totals)} of {n_pairs}] {a}/{b}: {total} ({explicit} explicit)')
        except RateLimitedError:
            output_filename = 'temp.csv'
            print('rate limited, aborting. incomplete results saved to \'temp.csv\'')
            break
    
    ships['fics'] = totals
    ships['explicit'] = n_explicit
    ships['p'] = ships['explicit'] / ships['fics']

    ships.to_csv(output_filename, index=False)
