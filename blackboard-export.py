#!/usr/bin/env python3
import requests
import xmltodict
from IPython import embed

import xml.etree.ElementTree as et
from pprint import pprint
from getpass import getpass
from os import path, makedirs

if __name__ == '__main__':
    BB_DOMAIN = 'https://blackboard.utexas.edu/webapps/Bb-mobile-BBLEARN'
    LOGIN_URL = 'https://blackboard.utexas.edu/webapps/login/'
    COURSES_URL = BB_DOMAIN + '/enrollments?course_type=COURSE'
    COURSE_MAP_URL = BB_DOMAIN + '/courseMap'
    COURSE_DATA_URL = BB_DOMAIN + '/courseData'

    EXPORT_PATH = 'courses'
    XML_CACHE_PATH = path.join(EXPORT_PATH, '.xmlcache')

    def cache_data(file_suffix):
        def actual_decorator(fun):
            def func_wrapper(*args, **kwargs):
                course = args[1]
                cache_file = path.join(XML_CACHE_PATH, course['@courseid']) + \
                        '-' + file_suffix + '.xml'
                if path.exists(cache_file):
                    with open(cache_file, 'rb') as cache:
                        return xmltodict.parse(cache)
                else:
                    course_data = fun(*args, **kwargs)
                    with open(cache_file, 'w') as cache:
                        cache.write(course_data)
                return xmltodict.parse(course_data)
            return func_wrapper
        return actual_decorator

    def get_course_data(session, course, course_section):
        query_params = {'course_id':course['@bbid'],
                        'course_section':course_section}
        return session.get(COURSE_DATA_URL, params=query_params).text

    @cache_data('coursemap')
    def get_course_map(session, course):
        query_params = {'course_id':course['@bbid']}
        return session.get(COURSE_MAP_URL, params=query_params).text

    @cache_data('announcements')
    def get_course_grades(session, course):
        return get_course_data(session, course, 'GRADES')

    @cache_data('grades')
    def get_course_announcements(session, course):
        return get_course_data(session, course, 'ANNOUNCEMENTS')

    USER_EID = input('Please enter your Blackboard username:')
    USER_PASSWORD = getpass('Please enter your Blackboard password:')

    makedirs(XML_CACHE_PATH, exist_ok=True)

    session = requests.Session()
    # authenticate the session
    print('Authenticating')
    session.post(LOGIN_URL, data={'user_id':USER_EID, 'password':USER_PASSWORD})

    # get courses user has been enrolled in
    print('Getting course list')
    courses_xml_text = session.get(COURSES_URL).text
    courses_xml = xmltodict.parse(courses_xml_text)
    courses = courses_xml['mobileresponse']['courses']['course']
    for course in courses:
        query_params = {'course_id':course['@bbid']}
        print('Getting', course['@name'])
        course_map = get_course_map(session, course)
        # make directory for course
        makedirs(path.join('courses', course['@courseid']), exist_ok=True)

        print('\tAnnouncements')
        announcements = get_course_announcements(session, course)

        print('\tGrades')
        grades = get_course_grades(session, course)

        print('\tFiles')
        print('\tAssignments')
