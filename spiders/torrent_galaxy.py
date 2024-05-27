import requests
from bs4 import BeautifulSoup
import re
import random
import datetime


class TorrentGalaxySpider:
    BASE_URL = 'https://torrentgalaxy.to'
    BASE_URL_TOR = 'http://galaxy3yrfbwlwo72q3v2wlyjinqr2vejgpkxb22ll5pcpuaxlnqjiid.onion/'

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
        return self.BASE_URL + torrent['provider_external_id'].lstrip('/')

    def get_forum_keys(self):
        return [1, 3, 42, 5, 6, 41]

    def get_topic(self, topic):
        if len(str(topic['id'])) < 2:
            return
        url = self.base_url + str(topic['id'])
        print("topic", url, str(topic['id']))
        res = self.session.get(url)

        soup = BeautifulSoup(res.text, 'html.parser')

        panels = soup.select('.panel')
        post = next((panel for panel in panels if 'torrent details' in panel.text.lower()), None)
        if not post:
            print('empty torrent details')

            return

        title_match = re.search(r'Torrent details for "(.*?)"', post.text)
        title = title_match.group(1) if title_match else ''

        imdb = self.get_imdb(post)
        if not imdb:
            print('No IMDB')
            imdb = self.get_imdb_by_title(title)
            if not imdb:
                return

        simular = post.find(lambda tag: tag.name == "h3" and "Similar torrents" in tag.text)
        if simular:
            simular_panel = simular.find_parent('div', class_='panel')
            simular_panel.decompose()

        quality = self.get_quality(title, post)
        magnet_match = re.search(r'"(magnet[^"]+)"', str(post))
        if not magnet_match:
            print('Not Magnet torrent')
            return
        url = magnet_match.group(1)

        files = self.get_files(soup)

        lang_element = next((row for row in post.select('div.tprow') if 'Language' in row.text), None)
        lang = lang_element.select_one('img').get('alt') if lang_element else 'English'
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
        url = f"{self.base_url}/torrents.php?cat={forum['id']}&page={forum['page'] - 1}"
        print(url)
        res = self.session.get(f"{self.base_url}/torrents.php", params={'cat': forum['id'], 'page': forum['page'] - 1})
        print(res)
        soup = BeautifulSoup(res.text, 'html.parser')

        table = soup.select_one('div.tgxtable')
        if not table:
            print('No table found')
            return
        lines = [row for row in table.select('div.tgxtablerow') if 'href="/torrent' in str(row)]

        after = datetime.datetime.now() - datetime.timedelta(hours=int(forum['last'])) if forum.get('last') else None
        exist = False

        for n, line in enumerate(lines):
            link_match = re.search(r'href="(/torrent/[^"]+)"', str(line))
            if link_match:
                time = None
                cells = line.select('div.tgxtablecell')
                for cell in cells:
                    if re.match(r'^\d{2}/\d{2}/\d{2} \d{2}:\d{2}$', cell.text.strip()):
                        time = datetime.datetime.strptime(cell.text.strip(), '%d/%m/%y %H:%M')

                if time and after and time < after:
                    continue

                seed = int(re.sub(r'[^0-9]', '', line.select_one('span[title] font').text))
                leech = int(re.sub(r'[^0-9]', '', line.select('span[title] font')[-1].text))

                yield {
                    'id': link_match.group(1),
                    'seed': seed,
                    'leech': leech,
                    'priority': n * 10 + random.randint(10, 20),
                }
                exist = True

        if not exist:
            return

        pages = soup.select('#pager')
        if pages:
            yield {
                'id': forum['id'],
                'page': forum['page'] + 1,
                'last': forum['last'],
                'interval': random.randint(1800, 3600),
            }

    def get_files(self, soup):
        file_elements = soup.select('#k1 tr')
        files = []
        for element in file_elements:
            name_element = element.select_one('td.table_col1')
            size_element = element.select_one('td.table_col2')

            if not name_element or not size_element:
                continue

            name = name_element.text.strip()
            size = self.approximate_size(size_element.text.strip())

            if size:
                files.append({'name': name, 'size': size})

        return files

    def get_imdb_by_title(self, title_str):
        title_str = title_str.replace('.', ' ')
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

        title_year_match = re.match(r'^(.*)\((\d{4})', title_str) or re.match(r'^(.*?) (\d{4})', title_str)
        if not title_year_match:
            return None

        name = title_year_match.group(1).strip()
        year = title_year_match.group(2).strip()

        if not name:
            return None

        return self.search_movie_by_title_and_year(name, year)

    def get_imdb(self, post):
        imdb_match = re.search(r'imdb\.com/title/(tt\d+)', str(post))
        return imdb_match.group(1) if imdb_match else None

    def get_quality(self, title, post):
        quality_match = re.search(r'(1080p|720p|480p|HDRip|BluRay|DVDRip)', title, re.IGNORECASE)
        return quality_match.group(1) if quality_match else None

    def lang_name_to_iso_code(self, lang):
        lang_map = {
            'English': 'en',
            'French': 'fr',
            'German': 'de',
            # Add more mappings as needed
        }
        return lang_map.get(lang, None)

    def get_episode_torrent_by_imdb(self, topic_id, imdb, season, episode):
        return {
            'topic_id': topic_id,
            'imdb': imdb,
            'season': season,
            'episode': episode,
        }

    def get_torrent_by_imdb(self, topic_id, imdb):
        return {
            'topic_id': topic_id,
            'imdb': imdb,
        }

    def update_torrent(self, torrent):
        # Implement your update logic here
        pass

    def approximate_size(self, size_str):

        size_str = size_str.strip()
        units = {
            'K': 1 / 1024 / 1024,
            'M': 1 / 1024,
            'G': 1,
            'T': 1024,
            "B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4
        }
        for unit in units:
            if size_str.endswith(unit):
                try:
                    number_part = size_str.replace(unit, '').strip()
                    return float(number_part) * units[unit]
                except ValueError:
                    continue
        return None


def search_show_by_title(self, title):
    # Implement your IMDb show search logic here
    pass


def search_movie_by_title_and_year(self, title, year):
    # Implement your IMDb movie search logic here
    pass


if __name__ == '__main__':
    tor_proxy = 'socks5h://127.0.0.1:7890'
    spider = TorrentGalaxySpider(tor_proxy, use_tor=False)
    forum = {'id': 1, 'page': 1, 'last': 24}  # Example forum data
    for topic in spider.get_page(forum):
        spider.get_topic(topic)
