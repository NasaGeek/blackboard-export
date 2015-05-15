#!/usr/bin/env python3
import requests
import xmltodict
from IPython import embed

import csv
from xml.parsers.expat import ExpatError
from xml.sax.saxutils import unescape
from pprint import pprint
from getpass import getpass
from os import path, makedirs
import functools

if __name__ == '__main__':
    BB_DOMAIN = 'https://blackboard.utexas.edu'
    BB_MOBILE_API = BB_DOMAIN + '/webapps/Bb-mobile-BBLEARN'
    LOGIN_URL = 'https://blackboard.utexas.edu/webapps/login/'
    COURSES_URL = BB_MOBILE_API + '/enrollments?course_type=COURSE'
    COURSE_MAP_URL = BB_MOBILE_API + '/courseMap'
    COURSE_DATA_URL = BB_MOBILE_API + '/courseData'
    CONTENT_DETAIL_URL = BB_MOBILE_API + '/contentDetail'

    EXPORT_PATH = 'courses'
    XML_CACHE_PATH = path.join(EXPORT_PATH, '.xmlcache')

    makedirs = functools.partial(makedirs, exist_ok=True)

    valid_path_char_map = str.maketrans(':\|/<>"?*', "------'--")

    def dict_to_list(fun):
        def func_wrapper(*args, **kwargs):
            dict_ = fun(*args, **kwargs)
            if isinstance(dict_, dict):
                return [dict_]
            else:
                return dict_
        return func_wrapper

    def unwrap_tags(keys):
        def actual_decorator(fun):
            def func_wrapper(*args, **kwargs):
                return functools.reduce(dict.get, keys, fun(*args, **kwargs))
            return func_wrapper
        return actual_decorator

    def cache_data(file_suffix_or_index):
        def actual_decorator(fun):
            def func_wrapper(*args, **kwargs):
                course = args[1]
                file_suffix = file_suffix_or_index
                if isinstance(file_suffix, int):
                    file_suffix = args[file_suffix]
                cache_file = path.join(XML_CACHE_PATH, course['@courseid']) + \
                        '-' + file_suffix + '.xml'
                should_download = True
                if path.exists(cache_file):
                    should_download = False
                    with open(cache_file, 'r', encoding='utf-8') as cache:
                        try:
                            return xmltodict.parse(cache.read())['mobileresponse']
                        except ExpatError:
                            # error when parsing, redownload
                            should_download = True
                if should_download:
                    course_data = fun(*args, **kwargs)
                    with open(cache_file, 'w', encoding='utf-8') as cache:
                        cache.write(course_data)
                    return xmltodict.parse(course_data)['mobileresponse']
            return func_wrapper
        return actual_decorator

    def get_course_data(session, course, course_section):
        query_params = {'course_id':course['@bbid'],
                        'course_section':course_section}
        return session.get(COURSE_DATA_URL, params=query_params).text

    @dict_to_list
    def dict_to_list_fun(dict_):
        return dict_

    @dict_to_list
    @unwrap_tags(['map','map-item'])
    @cache_data('coursemap')
    def get_course_map(session, course):
        query_params = {'course_id':course['@bbid']}
        return session.get(COURSE_MAP_URL, params=query_params).text

    @dict_to_list
    @unwrap_tags(['grades','grade-item'])
    @cache_data('grades')
    def get_course_grades(session, course):
        return get_course_data(session, course, 'GRADES')

    @dict_to_list
    @unwrap_tags(['announcements','announcement'])
    @cache_data('announcements')
    def get_course_announcements(session, course):
        return get_course_data(session, course, 'ANNOUNCEMENTS')

    @unwrap_tags(['content'])
    @cache_data(2)
    def get_content_detail(session, course, content_id):
        query_params = {'course_id':course['@bbid'], 'content_id':content_id}
        return session.get(CONTENT_DETAIL_URL, params=query_params).text

    @unwrap_tags(['courses','course'])
    @cache_data('courses')
    def get_courses(session, _):
        return session.get(COURSES_URL).text

    def parse_course_map(session, course, course_map, cwd):
        for map_item in course_map:
            if map_item['@isfolder'] == 'true':
                print('    Entering', map_item['@name'])
                new_cwd = path.join(cwd,
                        map_item['@name'].translate(valid_path_char_map))
                makedirs(new_cwd)
                if 'children' not in map_item:
                    # empty folder
                    break
                folder = dict_to_list_fun(map_item['children']['map-item'])
                parse_course_map(session, course, folder, new_cwd)
            elif map_item['@linktype'] in ['resource/x-bb-document', 'resource/x-bb-file']:
                # item is downloadable, have at it
                print('      Downloading', map_item['@name'])
                """
                TODO: item name can contain html, should I really be
                using it as the folder name?
                """
                content_path = path.join(cwd, map_item['@name'].translate(valid_path_char_map))
                makedirs(content_path)
                content_detail = get_content_detail(session, course,
                        map_item['@contentid'])
                if content_detail.get('body'):
                    try:
                        # write content description out to an html file
                        with open(path.join(content_path, 'description.html'),
                                'x', encoding='utf-8') as description:
                            """
                            FIXME: text gets corrupted sometimes, specific example:
                            course:_142609_1 content:_4428774_1 apostrophe gets
                            mangled
                            """
                            description.write(content_detail['body'])
                    except FileExistsError:
                        # file already exists, don't write again
                        pass
                if content_detail.get('attachments',{}).get('attachment'):
                    attachments = dict_to_list_fun(content_detail['attachments']['attachment'])
                    for attachment in attachments:
                        try:
                            with open(path.join(content_path,
                                attachment['@name'].translate(valid_path_char_map)), 'xb') as destination:
                                download = session.get(BB_DOMAIN +
                                    unescape(attachment['@uri']))
                                destination.write(download.content)
                        except FileExistsError:
                            # file already exists, don't download again
                            pass
            else:
                # nothing of interest
                pass

    def parse_announcements(announcements, base_path):
        announcements_path = path.join(base_path, 'announcements')
        makedirs(announcements_path)
        for announcement in announcements:
            filename = announcement['@startdate'] + ' - ' + announcement['@subject'] + '.html'
            filename = filename.translate(valid_path_char_map)
            try:
                with open(path.join(announcements_path, filename), 'x',
                        encoding='utf-8') as outfile:
                    #TODO: convert to markdown?
                    outfile.write(announcement.get('#text', 'No announcement text'))
                    if '@userdisplayname' in announcement:
                        outfile.write('\n' + announcement['@userdisplayname'])
            except FileExistsError:
                pass

    def parse_grades(grades, base_path):
        try:
            with open(path.join(base_path, 'grades.csv'), 'x', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Name', 'Grade', 'ScoreValue', 'Points Possible',
                    'Category', 'Average', 'Median', 'Comments'])
                columnkeys = ['@name', '@grade', '@scoreValue', '@pointspossible',
                    '@gradeBookType', '@average', '@median', '@comments']
                for grade in grades:
                    writer.writerow([grade.get(key) for key in columnkeys])
        except FileExistsError:
            pass

    USER_EID = input('Please enter your Blackboard username:')
    USER_PASSWORD = getpass('Please enter your Blackboard password:')

    makedirs(XML_CACHE_PATH)

    session = requests.Session()
    # authenticate the session
    print('Authenticating')
    session.post(LOGIN_URL, data={'user_id':USER_EID, 'password':USER_PASSWORD})

    # get courses user has been enrolled in
    print('Getting course list')
    courses = get_courses(session, {'@courseid': 'courses'})
    for course in courses:
        course_path = path.join('courses', course['@courseid'].translate(valid_path_char_map))
        print('Getting', course['@name'])
        course_map = get_course_map(session, course)
        # make directory for course
        makedirs(course_path)

        print('  Announcements')
        announcements = get_course_announcements(session, course)
        if announcements:
            parse_announcements(announcements, course_path)

        print('  Grades')
        grades = get_course_grades(session, course)
        if grades:
            parse_grades(grades, course_path)

        print('  Files')
        files_path = path.join(course_path, 'files')
        makedirs(files_path)
        parse_course_map(session, course, course_map, files_path)

        print('  Assignments')
