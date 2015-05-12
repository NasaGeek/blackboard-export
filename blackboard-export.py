#!/usr/bin/env python3
import requests
import xmltodict

import xml.etree.ElementTree as et
from pprint import pprint
from getpass import getpass

def get_course_data(session, course_id, course_section):
    query_params = {'course_id':course_id, 'course_section':course_section}
    return xmltodict.parse(session.get(COURSE_DATA_URL, params=query_params).text)

if __name__ == '__main__':
    BB_DOMAIN = 'https://blackboard.utexas.edu/webapps/Bb-mobile-BBLEARN'
    LOGIN_URL = 'https://blackboard.utexas.edu/webapps/login/'
    COURSES_URL = BB_DOMAIN + '/enrollments?course_type=COURSE'
    COURSE_MAP_URL = BB_DOMAIN + '/courseMap'
    COURSE_DATA_URL = BB_DOMAIN + '/courseData'

    USER_EID = input('Please enter your Blackboard username:')
    USER_PASSWORD = getpass('Please enter your Blackboard password:')

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
        course_id = course['@bbid']
        query_params = {'course_id':course['@bbid']}
        print('Getting', course['@name'])
        course_map = xmltodict.parse(session.get(COURSE_MAP_URL,
            params=query_params).text)
        pprint(course_map)

        print('\tFiles')

        print('\tAnnouncements')
        announcements = get_course_data(session, course_id, 'ANNOUNCEMENTS')
        pprint(announcements)

        print('\tGrades')
        grades = get_course_data(session, course_id, 'GRADES')
        pprint(grades)

        print('\tAssignments')
