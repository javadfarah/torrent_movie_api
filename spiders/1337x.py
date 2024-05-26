import requests
from bs4 import BeautifulSoup
import datetime
import re
import json
from urllib.parse import urljoin
import random


class T1337xSpider:
    BASE_URL = 'https://1337x.to/'
    BASE_URL_TOR = 'http://l337xdarkkaqfwzntnfk5bmoaroivtl6xsbatabvlb52umg6v3ch44yd.onion/'

    def __init__(self, proxy=None, use_tor=False):
        self.use_tor = use_tor
        self.session = requests.Session()
        self.session.headers.update({
            'Accept-Encoding': 'gzip',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        if proxy:
            self.session.proxies = {
                'http': proxy,
                'https': proxy,
            }
        if self.use_tor:
            self.base_url = self.BASE_URL_TOR
        else:
            print("no tor")
            self.base_url = self.BASE_URL
        self.session.cookies = requests.cookies.RequestsCookieJar()

    def get_priority(self, torrent):
        return -10

    def get_source(self, torrent):
        return urljoin(self.BASE_URL, torrent.get('provider_external_id').lstrip('/'))

    def get_forum_keys(self):
        return ['Movies', 'TV']

    def get_topic(self, topic):
        res = self.session.get(urljoin(self.base_url, topic['id']))
        soup = BeautifulSoup(res.text, 'html.parser')

        post = soup.select_one('#description')
        title_element = soup.select_one('.box-info-heading h1')
        if title_element is None:
            print('Title element not found')
            return

        title = title_element.text.strip()

        imdb = self.get_imdb(post)
        if not imdb:
            print('No IMDB found')
            imdb = self.get_imdb_by_title(title)
            if not imdb:
                return

        quality = self.get_quality(title, post)

        torrent_table = soup.select_one('.torrent-detail-page')
        magnet_link_match = re.search(r'"(magnet:[^"]+)"', torrent_table.decode())
        if not magnet_link_match:
            print('Not Magnet torrent')
            return
        url = magnet_link_match.group(1)

        files = self.get_files(soup)

        lang_element = next((li for li in soup.select('ul.list li') if 'Language' in li.text), None)
        lang = lang_element.select_one('span').text.strip() if lang_element else None
        language = self.lang_name_to_iso_code(lang)
        if not language:
            return

        season_episode_match = re.search(r'S(\d\d)E(\d\d)', title)
        if season_episode_match:
            torrent = self.get_episode_torrent_by_imdb(topic['id'], imdb, int(season_episode_match.group(1)),
                                                       int(season_episode_match.group(2)))
        else:
            torrent = self.get_torrent_by_imdb(topic['id'], imdb)

        if not torrent:
            return

        torrent.update({
            'provider_title': title,
            'url': url,
            'seed': topic['seed'],
            'peer': topic['seed'] + topic['leech'],
            'quality': quality,
            'language': language,
            'files': files,
        })

        self.update_torrent(torrent)

    def get_page(self, forum):
        url = urljoin(self.base_url, f"/cat/{forum['id']}/{forum['page']}/")
        print(url)
        res = self.session.get(url)
        print(res)
        soup = BeautifulSoup(res.text, 'html.parser')

        table = soup.select_one('.featured-list table')
        lines = [tr for tr in table.select('tr') if 'href="/torrent' in tr.decode()]

        after = datetime.datetime.now() - datetime.timedelta(hours=int(forum['last'])) if forum.get('last') else None
        exist = False

        for n, line in enumerate(lines):
            torrent_link_match = re.search(r'href="(/torrent/[^"]+)"', line.decode())
            if torrent_link_match:
                time_string = line.select_one('td.coll-date').text.strip().replace("'", '')
                try:
                    time = datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    time = None
                if time and after and time < after:
                    continue

                seed = int(re.sub(r'[^0-9]', '', line.select_one('td.seeds').text.strip()))
                leech = int(re.sub(r'[^0-9]', '', line.select_one('td.leeches').text.strip()))

                yield {
                    'id': torrent_link_match.group(1),
                    'seed': seed,
                    'leech': leech,
                    'priority': n * 10 + random.randint(10, 20),
                }
                exist = True

        if exist:
            pages = soup.select('.pagination')
            if 'Last' in pages[0].decode():
                yield {
                    'id': forum['id'],
                    'page': forum['page'] + 1,
                    'last': forum['last'],
                    'interval': random.randint(1800, 3600),
                }

    def get_files(self, soup):
        file_elements = soup.select('#files > ul')
        files = self.process_file_tree(file_elements)
        return list(filter(None, files))

    def process_file_tree(self, elements, dir_name=''):
        files = []
        for element in elements:
            if element.previous_sibling and hasattr(element.previous_sibling, 'get') and 'head' in element.previous_sibling.get('class', []):
                dir_name = element.previous_sibling.text.strip() + '/'

            sub_dirs = element.select('ul')
            for sub_dir in sub_dirs:
                files.extend(self.process_file_tree([sub_dir], dir_name))

            items = element.select('li')
            for item in items:
                name_match = re.match(r'(.*?)\((.*?)\)', item.text)
                if name_match:
                    name = name_match.group(1).strip()
                    size = self.approximate_size(name_match.group(2).strip())
                    files.append({'name': dir_name + name, 'size': size})
        return files

    def get_imdb_by_title(self, title):
        title_str = title.replace('.', ' ')
        is_serial = 'Season' in title_str or re.search(r'S\d\dE\d\d', title_str)

        year_match = re.search(r'\((\d{4})\)', title_str)
        year = year_match.group(1) if year_match else None
        if not year:
            is_serial = True

        if is_serial:
            name_match = re.search(r'(.*?)(S\d\d|Season \d)', title_str)
            if name_match:
                name = name_match.group(1).strip()
                return self.search_show_by_title(name)

        title_year_match = re.match(r'^(.*)\((\d{4})', title_str)
        if not title_year_match:
            title_year_match = re.match(r'^(.*?) (\d{4})', title_str)
        if not title_year_match:
            return None

        name = title_year_match.group(1).strip()
        year = title_year_match.group(2).strip()

        if not name:
            return None

        return self.search_movie_by_title_and_year(name, year)

    def get_imdb(self, post):
        # Placeholder logic to extract IMDB ID from the post
        # Implement this according to your parsing logic
        imdb_match = re.search(r'imdb\.com/title/(tt\d+)', post.decode())
        return imdb_match.group(1) if imdb_match else None

    def get_quality(self, title, post):
        # Placeholder logic to extract quality from the title or post
        # Implement this according to your parsing logic
        quality_match = re.search(r'(1080p|720p|480p|HDRip|BluRay|DVDRip)', title, re.IGNORECASE)
        return quality_match.group(1) if quality_match else None

    def lang_name_to_iso_code(self, lang):
        # Placeholder logic to convert language name to ISO code
        # Implement this according to your language conversion logic
        lang_map = {
            'English': 'en',
            'French': 'fr',
            'German': 'de',
            # Add more mappings as needed
        }
        return lang_map.get(lang, None)

    def get_episode_torrent_by_imdb(self, topic_id, imdb, season, episode):
        # Placeholder logic to get episode torrent by IMDB ID
        # Implement this according to your database or service logic
        # For demonstration, returning a dummy dictionary
        return {
            'topic_id': topic_id,
            'imdb': imdb,
            'season': season,
            'episode': episode,
        }

    def get_torrent_by_imdb(self, topic_id, imdb):
        # Placeholder logic to get torrent by IMDB ID
        # Implement this according to your database or service logic
        # For demonstration, returning a dummy dictionary
        return {
            'topic_id': topic_id,
            'imdb': imdb,
        }

    def update_torrent(self, torrent):
        # Placeholder logic to update torrent
        # Implement this according to your database or service logic
        print(f"Updating torrent: {json.dumps(torrent, indent=2)}")

    def search_show_by_title(self, name):
        # Placeholder logic to search show by title
        # Implement this according to your database or service logic
        # For demonstration, returning a dummy IMDB ID
        return 'tt1234567'

    def search_movie_by_title_and_year(self, name, year):
        # Placeholder logic to search movie by title and year
        # Implement this according to your database or service logic
        # For demonstration, returning a dummy IMDB ID
        return 'tt7654321'

    def approximate_size(self, size_str):
        # Placeholder logic to approximate size from string
        # Implement this according to your parsing logic
        size_match = re.match(r'(\d+(?:\.\d+)?)\s*(GB|MB)', size_str)
        if size_match:
            size, unit = size_match.groups()
            size = float(size)
            if unit == 'GB':
                return int(size * 1024 * 1024 * 1024)
            elif unit == 'MB':
                return int(size * 1024 * 1024)
        return 0


if __name__ == '__main__':
    tor_proxy = 'socks5h://127.0.0.1:7890'
    spider = T1337xSpider(tor_proxy, use_tor=False)

    # Example forum and topic data
    forum = {
        'id': 'Movies',
        'page': 1,
        'last': 24  # Get posts from the last 24 hours
    }

    print("Fetching topics...")
    topics = list(spider.get_page(forum))
    if not topics:
        print("No topics found.")

    # Processing each topic
    for topic in topics:
        print(f"Processing topic: {topic['id']}")
        spider.get_topic(topic)
