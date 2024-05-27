import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime
import json


class Yts:
    BASE_URL = 'https://yts.mx/'

    def __init__(self, proxy=None):
        self.client = requests.Session()
        self.client.headers.update({'User-Agent': 'Mozilla/5.0'})
        if proxy:
            self.client.proxies = {
                'http': proxy,
                'https': proxy,
            }

    def get_source(self, torrent):
        return f"{self.BASE_URL}browse-movies/{torrent['provider_title']}/all/all/0/latest/{torrent['media']['year']}/all"

    def get_priority(self, torrent):
        return 10 if torrent['language'] == 'en' else -10

    def get_forum_keys(self):
        return [1]

    def get_page(self, forum):
        url = f"{self.BASE_URL}api/v2/list_movies.json"
        print(url)
        res = self.client.get(url, params={
            'limit': 50,
            'page': forum['page'],
        })
        data = res.json()
        if not data['data']['movies']:
            return

        for movie_data in data['data']['movies']:
            for torrent_data in movie_data['torrents']:
                self.build_torrent_from_data(movie_data, torrent_data)

    def has_new_torrents(self, data, after):
        for movie_data in data['data']['movies']:
            for torrent_data in movie_data['torrents']:
                print(torrent_data['date_uploaded_unix'])
                print(after.timestamp())
                if after.timestamp() < torrent_data['date_uploaded_unix']:
                    return True
        return False

    def get_topic(self, topic):
        movie_id = topic['id'].split(':')[0]
        res = self.client.get(f"{self.BASE_URL}api/v2/movie_details.json", params={
            'movie_id': movie_id,
        })
        data = res.json()

        if not data['data']['movie']:
            return
        movie_data = data['data']['movie']
        media = self.get_media_by_imdb(movie_data['imdb_code'])
        if not media:
            return

        for torrent_data in movie_data['torrents']:
            self.build_torrent_from_data(media, movie_data, torrent_data)

    def build_torrent_from_data(self, movie_data, torrent_data):
        url = f"magnet:?xt=urn:btih:{torrent_data['hash']}&" + '&'.join([
            f"tr={item}" for item in [
                'udp://tracker.opentrackr.org:1337',
                'udp://tracker.tiny-vps.com:6969',
                'udp://tracker.openbittorrent.com:1337',
                'udp://tracker.coppersurfer.tk:6969',
                'udp://tracker.leechers-paradise.org:6969',
                'udp://p4p.arenabg.ch:1337',
                'udp://p4p.arenabg.com:1337',
                'udp://tracker.internetwarriors.net:1337',
                'udp://9.rarbg.to:2710',
                'udp://9.rarbg.me:2710',
                'udp://exodus.desync.com:6969',
                'udp://tracker.cyberia.is:6969',
                'udp://tracker.torrent.eu.org:451',
                'udp://open.stealth.si:80',
                'udp://tracker.moeking.me:6969',
                'udp://tracker.zerobytes.xyz:1337',
            ]
        ])

        torrent = {
            'url': url,
            'seed': torrent_data['seeds'],
            'peer': torrent_data['peers'],
            'quality': torrent_data['quality'],
            'language': movie_data['language'],
            'size': torrent_data['size_bytes']
        }
        print(torrent)
        self.update_torrent(torrent)

    def update_torrent(self, torrent):
        # This method should update the torrent in the database.
        # The implementation is omitted here since it depends on the application specifics.
        pass

    def get_media_by_imdb(self, imdb_code):
        # This method should return media information based on the IMDb code.
        # The implementation is omitted here since it depends on the application specifics.
        pass


# Example usage:
if __name__ == '__main__':
    tor_proxy = 'socks5h://127.0.0.1:7890'

    yts = Yts(tor_proxy)
    forum = {
        'id': 1,
        'page': 1,
        'last': '2024-04-27 10:00:00'
    }
    for page in yts.get_page(forum):
        print(page)
