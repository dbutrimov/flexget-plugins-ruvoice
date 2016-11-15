# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, absolute_import
from builtins import *  # pylint: disable=unused-import, redefined-builtin

import os
import importlib.util
import re
import logging
from time import sleep
from bs4 import BeautifulSoup

from flexget import plugin
from flexget.entry import Entry
from flexget.event import event
from flexget.utils import requests


dir_path = os.path.dirname(os.path.abspath(__file__))

module_path = os.path.join(dir_path, 'baibako_utils.py')
spec = importlib.util.spec_from_file_location('baibako_utils', module_path)
baibako_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baibako_utils)


log = logging.getLogger('baibako_search')

table_class_regexp = re.compile(r'table.*', flags=re.IGNORECASE)
episode_title_regexp = re.compile(
    r'^([^/]*?)\s*/\s*([^/]*?)\s*/\s*s(\d+)e(\d+)(?:-(\d+))?\s*/\s*([^/]*?)\s*(?:(?:/.*)|$)',
    flags=re.IGNORECASE)


class BaibakoShow(object):
    titles = []
    url = ''

    def __init__(self, titles, url):
        self.titles = titles
        self.url = url


class BaibakoSearch(object):
    """Usage:

    baibako_search:
      serial_tab: 'hd720' or 'hd1080' or 'x264' or 'xvid' or 'all'
    """

    schema = {
        'type': 'object',
        'properties': {
            'serial_tab': {'type': 'string'}
        },
        'additionalProperties': False
    }

    def search(self, task, entry, config=None):
        entries = set()

        serials_url = 'http://baibako.tv/serials.php'

        log.debug("Fetching serials page `{0}`...".format(serials_url))

        try:
            serials_response = task.requests.get(serials_url)
        except requests.RequestException as e:
            log.error("Error while fetching page: {0}".format(e))
            sleep(3)
            return None
        serials_html = serials_response.text
        sleep(3)

        shows = set()

        serials_tree = BeautifulSoup(serials_html, 'html.parser')
        serials_table_node = serials_tree.find('table', class_=table_class_regexp)
        if not serials_table_node:
            log.error('Error while parsing serials page: node <table class=`table.*`> are not found')
            return None

        serial_link_nodes = serials_table_node.find_all('a')
        for serial_link_node in serial_link_nodes:
            serial_title = serial_link_node.text
            serial_link = serial_link_node.get('href')
            serial_link = baibako_utils.add_host_if_need(serial_link)

            show = BaibakoShow([serial_title], serial_link)
            shows.add(show)

        log.debug("{0:d} show(s) are found".format(len(shows)))

        serial_tab = config.get('serial_tab', 'all')

        search_string_regexp = re.compile(r'^(.*?)\s*s(\d+)e(\d+)$', flags=re.IGNORECASE)
        episode_link_regexp = re.compile(r'details.php\?id=(\d+)', flags=re.IGNORECASE)

        for search_string in entry.get('search_strings', [entry['title']]):
            search_match = search_string_regexp.search(search_string)
            if not search_match:
                continue

            search_title = search_match.group(1)
            search_season = int(search_match.group(2))
            search_episode = int(search_match.group(3))

            for show in shows:
                if search_title not in show.titles:
                    continue

                serial_url = show.url + '&tab=' + serial_tab
                try:
                    serial_response = task.requests.get(serial_url)
                except requests.RequestException as e:
                    log.error("Error while fetching page: {0}".format(e))
                    sleep(3)
                    continue
                serial_html = serial_response.text
                sleep(3)

                serial_tree = BeautifulSoup(serial_html, 'html.parser')
                serial_table_node = serial_tree.find('table', class_=table_class_regexp)
                if not serial_table_node:
                    log.error('Error while parsing serial page: node <table class=`table.*`> are not found')
                    continue

                link_nodes = serial_table_node.find_all('a', href=episode_link_regexp)
                for link_node in link_nodes:
                    link_title = link_node.text
                    episode_title_match = episode_title_regexp.search(link_title)
                    if not episode_title_match:
                        log.verbose("Error while parsing serial page: title `{0}` are not matched".format(link_title))
                        continue

                    season = int(episode_title_match.group(3))
                    first_episode = int(episode_title_match.group(4))
                    last_episode = first_episode
                    last_episode_group = episode_title_match.group(5)
                    if last_episode_group:
                        last_episode = int(last_episode_group)

                    if season != search_season or (first_episode > search_episode or last_episode < search_episode):
                        continue

                    ru_title = episode_title_match.group(1)
                    title = episode_title_match.group(2)
                    quality = episode_title_match.group(6)

                    if last_episode > first_episode:
                        episode_id = 's{0:02d}e{1:02d}-e{2:02d}'.format(season, first_episode, last_episode)
                    else:
                        episode_id = 's{0:02d}e{1:02d}'.format(season, first_episode)

                    entry_title = "{0} / {1} / {2} / {3}".format(title, ru_title, episode_id, quality)
                    entry_url = link_node.get('href')
                    entry_url = baibako_utils.add_host_if_need(entry_url)

                    entry = Entry()
                    entry['title'] = entry_title
                    entry['url'] = entry_url

                    entries.add(entry)

        return entries


@event('plugin.register')
def register_plugin():
    plugin.register(BaibakoSearch, 'baibako_search', groups=['search'], api_ver=2)