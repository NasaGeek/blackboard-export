#!/usr/bin/env python3
"""Script to download all significant information from a user's courses on the
Blackboard Learn LMS.
"""
import requests
import xmltodict

import csv
from xml.parsers.expat import ExpatError
from xml.sax.saxutils import unescape
from getpass import getpass
from os import path, makedirs
import functools

BB_DOMAIN = 'https://blackboard.utexas.edu'
BB_MOBILE_API = BB_DOMAIN + '/webapps/Bb-mobile-BBLEARN'
LOGIN_URL = 'https://blackboard.utexas.edu/webapps/login/'
COURSES_URL = BB_MOBILE_API + '/enrollments?course_type=COURSE'
COURSE_MAP_URL = BB_MOBILE_API + '/courseMap'
COURSE_DATA_URL = BB_MOBILE_API + '/courseData'
CONTENT_DETAIL_URL = BB_MOBILE_API + '/contentDetail'

EXPORT_PATH = 'courses'
XML_CACHE_PATH = path.join(EXPORT_PATH, '.xmlcache')

DOWNLOADABLE_LINKTYPES = ['resource/x-bb-assignment',
                          'resource/x-bb-document', 'resource/x-bb-file']
GRADE_COLUMN_KEYS = ['@name', '@grade', '@scoreValue', '@pointspossible',
                     '@gradeBookType', '@average', '@median', '@comments']
GRADE_COLUMN_HEADERS = ['Name', 'Grade', 'ScoreValue', 'Points Possible',
                        'Category', 'Average', 'Median', 'Comments']
VALID_PATH_CHAR_MAP = str.maketrans(r':\|/<>"?*', "------'--")

makedirs = functools.partial(makedirs, exist_ok=True)


def ensure_list(fun):
    """Decorator to ensure that the wrapped function always returns a list.

    This exists because xmltodict will return a dict if there is only one
    instance of an xml element, but it will returns a list of dicts if there
    are multiple elements with the the same name.
    """
    @functools.wraps(fun)
    def func_wrapper(*args, **kwargs):
        list_ = fun(*args, **kwargs)
        if list_ and not isinstance(list_, list):
            return [list_]
        else:
            return list_
    return func_wrapper


def strip_keys(keys):
    """Decorator to strip keys from a dict like dict[key1][key2]...

    Keys are stripped off in the order they are given in the `keys` list.
    """
    def actual_decorator(fun):
        @functools.wraps(fun)
        def func_wrapper(*args, **kwargs):
            return functools.reduce(dict.get, keys, fun(*args, **kwargs))
        return func_wrapper
    return actual_decorator


def cache_data(file_suffix_or_index):
    """Decorator to use a file cache for the result of the wrapped function.

    Results are written to and read from xml files stored at XML_CACHE_PATH.
    The name of each file consists of the course_id with some string appended
    to it. If `file_suffix_or_index` is a string, then that string is appended;
    if it is an int, then it will be used as an index into the wrapped
    function's positional arguments, and that argument (presumably a string)
    will be appended.
    """
    def actual_decorator(fun):
        @functools.wraps(fun)
        def func_wrapper(*args, **kwargs):
            course = args[1]
            file_suffix = file_suffix_or_index
            if isinstance(file_suffix, int):
                file_suffix = args[file_suffix]
            cache_file_path = '{}-{}.xml'.format(
                path.join(XML_CACHE_PATH, course['@courseid']),
                file_suffix)
            should_download = True
            if path.exists(cache_file_path):
                should_download = False
                with open(cache_file_path, 'r', encoding='utf-8') as cache:
                    try:
                        return xmltodict.parse(cache.read())
                    except ExpatError:
                        # error when parsing, redownload
                        should_download = True
            if should_download:
                course_data = fun(*args, **kwargs)
                with open(cache_file_path, 'w', encoding='utf-8') as cache:
                    cache.write(course_data)
                return xmltodict.parse(course_data)
        return func_wrapper
    return actual_decorator


def get_course_data(session, course, course_section):
    """Query Blackboard's mobile API for a section of the given `course`.

    :param requests.Session session: Session used to perform the request, must
        be authenticated with Blackboard
    :param dict course: Blackboard course whose section is being queried
    :param str course_section: Section of the course to fetch, known sections
        are ANNOUNCEMENTS, GRADES, BLOGS, GROUPS, JOURNALS, FORUMS, and TASKS
    """
    query_params = {'course_id': course['@bbid'],
                    'course_section': course_section}
    return session.get(COURSE_DATA_URL, params=query_params).text


@ensure_list
@strip_keys(['mobileresponse', 'map', 'map-item'])
@cache_data('coursemap')
def get_course_map(session, course):
    """Query Blackboard's mobile API for the given course's course map.

    :param requests.Session session: Session used to perform the request, must
        be authenticated with Blackboard
    :param dict course: Blackboard course whose course map is being queried
    """
    query_params = {'course_id': course['@bbid']}
    return session.get(COURSE_MAP_URL, params=query_params).text


@ensure_list
@strip_keys(['mobileresponse', 'grades', 'grade-item'])
@cache_data('grades')
def get_course_grades(session, course):
    """Query Blackboard's mobile API for the given course's grades.

    :param requests.Session session: Session used to perform the request, must
        be authenticated with Blackboard
    :param dict course: Blackboard course whose grades are being queried
    """
    return get_course_data(session, course, 'GRADES')


@ensure_list
@strip_keys(['mobileresponse', 'announcements', 'announcement'])
@cache_data('announcements')
def get_course_announcements(session, course):
    """Query Blackboard's mobile API for the given course's announcements.

    :param requests.Session session: Session used to perform the request, must
        be authenticated with Blackboard
    :param dict course: Blackboard course whose announcements are being queried
    """
    return get_course_data(session, course, 'ANNOUNCEMENTS')


@strip_keys(['mobileresponse', 'content'])
@cache_data(2)
def get_content_detail(session, course, content_id):
    """Query Blackboard's mobile API for content from the given course.

    :param requests.Session session: Session used to perform the request, must
        be authenticated with Blackboard
    :param dict course: Blackboard course whose announcements are being queried
    :param str content_id: ID of the content being queried, found in the course
        map
    """
    query_params = {'course_id': course['@bbid'], 'content_id': content_id}
    return session.get(CONTENT_DETAIL_URL, params=query_params).text


@strip_keys(['mobileresponse', 'courses', 'course'])
@cache_data('courses')
def get_courses(session, _):
    """Query Blackboard's mobile API for a user's courses.

    :param request.Session session: Session used to perform the request, must
        be authenticated with Blackboard
    :param _: Hacky parameter for compatibility with the cache_data decorator
    """
    return session.get(COURSES_URL).text


def parse_course_map(session, course, course_map, cwd):
    """Download all the downloadable items found in the given `course_map`.

    :param requests.Session session: Session used to perform download requests,
        must be authenticated with Blackboard
    :param dict course: Blackboard course whose course map is being parsed
    :param dict course_map: Course map whose items are to be downloaded
    :param str cwd: Base path to save course map to
    """
    for map_item in course_map:
        if map_item['@isfolder'] == 'true':
            print('    Entering', map_item['@name'])
            new_cwd = path.join(
                cwd,
                map_item['@name'].translate(VALID_PATH_CHAR_MAP))
            makedirs(new_cwd)
            if 'children' not in map_item:
                # empty folder
                break
            folder = ensure_list(lambda _: _)(map_item['children']['map-item'])
            parse_course_map(session, course, folder, new_cwd)
        elif map_item['@linktype'] in DOWNLOADABLE_LINKTYPES:
            # item is downloadable, have at it
            print('      Downloading', map_item['@name'])
            # TODO: item name can contain html, should I really be using it as
            # the folder name?
            content_path = path.join(
                cwd,
                map_item['@name'].translate(VALID_PATH_CHAR_MAP))
            makedirs(content_path)
            content_detail = get_content_detail(
                session,
                course,
                map_item['@contentid'])
            if content_detail.get('body'):
                try:
                    # write content description out to an html file
                    with open(path.join(content_path, 'description.html'),
                              'x', encoding='utf-8') as description:
                        # FIXME: text gets corrupted sometimes, specific
                        # example: course:_142609_1 content:_4428774_1
                        # apostrophe gets mangled
                        description.write(content_detail['body'])
                except FileExistsError:
                    # file already exists, don't write again
                    pass
            if content_detail.get('attachments', {}).get('attachment'):
                attachments = ensure_list(
                    lambda _: _)(content_detail['attachments']['attachment'])
                for attachment in attachments:
                    attachment_path = path.join(
                        content_path,
                        attachment['@name'].translate(VALID_PATH_CHAR_MAP))
                    try:
                        with open(attachment_path, 'xb') as destination:
                            download = session.get(
                                BB_DOMAIN + unescape(attachment['@uri']))
                            destination.write(download.content)
                    except FileExistsError:
                        # file already exists, don't download again
                        pass
        else:
            # nothing of interest
            pass


def parse_announcements(announcements, base_path):
    """Parse the `announcements` list, saving each item to its own html file.

    :param list announcements: Announcements that are to be parsed and saved
    :param str base_path: Path to save announcement files to
    """
    announcements_path = path.join(base_path, 'announcements')
    makedirs(announcements_path)
    for announcement in announcements:
        filename = '{} - {}.html'.format(
            announcement['@startdate'],
            announcement['@subject'])
        filename = filename.translate(VALID_PATH_CHAR_MAP)
        try:
            with open(path.join(announcements_path, filename), 'x',
                      encoding='utf-8') as outfile:
                # TODO: convert to markdown?
                outfile.write(
                    announcement.get('#text', 'No announcement text'))
                if '@userdisplayname' in announcement:
                    outfile.write('\n' + announcement['@userdisplayname'])
        except FileExistsError:
            pass


def parse_grades(grades, base_path):
    """Parse the `grades` list, saving the grades to a csv file.

    :param list grades: Grades that are to be parsed and saved
    :param str base_path: Path to save grade csv to
    """
    try:
        with open(path.join(base_path, 'grades.csv'), 'x', newline='') \
                as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(GRADE_COLUMN_HEADERS)
            for grade in grades:
                writer.writerow(
                    [grade.get(key) for key in GRADE_COLUMN_KEYS])
    except FileExistsError:
        pass


def main():
    user_eid = input('Please enter your Blackboard username:')
    user_password = getpass('Please enter your Blackboard password:')

    makedirs(XML_CACHE_PATH)

    session = requests.Session()
    # authenticate the session
    print('Authenticating')
    session.post(LOGIN_URL, data={
        'user_id': user_eid,
        'password': user_password})

    # get courses user has been enrolled in
    print('Getting course list')
    courses = get_courses(session, {'@courseid': 'courses'})
    for course in courses:
        course_path = path.join(
            'courses',
            course['@courseid'].translate(VALID_PATH_CHAR_MAP))
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


if __name__ == '__main__':
    main()
