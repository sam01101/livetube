"""
    livetube - A API for youtube streaming
    Author: Sam
    Created: 2020/12/18 12:57
    File:    parser.py
    Description: 
"""
import json
import re
from ast import literal_eval
from html.parser import HTMLParser

from livetube.util.exceptions import HTMLParseError


def parse_for_object(html: str, preceding_regex: str) -> dict:
    """Parses input html to find the end of a JavaScript object.

    :param str html:
        HTML to be parsed for an object.
    :param str preceding_regex:
        Regex to find the string preceding the object.
    :rtype dict:
    :returns:
        A dict created from parsing the object.
    """
    regex = re.compile(preceding_regex)
    result = regex.search(html)
    if not result:
        raise HTMLParseError(f'No matches for regex {preceding_regex}')

    start_index = result.span()[1]
    return parse_for_object_from_startpoint(html, start_index)


def parse_for_object_from_startpoint(html: str, start_point: int) -> dict:
    """Parses input html to find the end of a JavaScript object.

    :param str html:
        HTML to be parsed for an object.
    :param int start_point:
        Index of where the object starts.
    :rtype dict:
    :returns:
        A dict created from parsing the object.
    """
    html = html[start_point:]
    if html[0] != '{':
        raise HTMLParseError('Invalid start point.')

    # First letter MUST be a open brace, so we put that in the stack,
    # and skip the first character.
    stack = ['{']
    i = 1

    context_closers = {
        '{': '}',
        '[': ']',
        '"': '"'
    }

    while i < len(html):
        if len(stack) == 0:
            break
        curr_char = html[i]
        curr_context = stack[-1]

        # If we've reached a context closer, we can remove an element off the stack
        if curr_char == context_closers[curr_context]:
            stack.pop()
            i += 1
            continue

        # Strings require special context handling because they can contain
        #  context openers *and* closers
        if curr_context == '"':
            # If there's a backslash in a string, we skip a character
            if curr_char == '\\':
                i += 2
                continue
        else:
            # Non-string contexts are when we need to look for context openers.
            if curr_char in context_closers.keys():
                stack.append(curr_char)

        i += 1

    full_obj = html[:i]
    try:
        return json.loads(full_obj)
    except json.decoder.JSONDecodeError:
        try:
            return literal_eval(full_obj)
        except ValueError:
            raise HTMLParseError('Could not parse object.')


class ScriptTaker(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.scripts = []
        self.next_is_script = False
        self.feed(html)

    def error(self, message):
        pass

    def handle_starttag(self, tag, data):
        if tag == "script":
            for key, _ in data:
                if key == "src":
                    return
            self.next_is_script = True

    def handle_data(self, data: str):
        if self.next_is_script:
            self.next_is_script = False
            if data.startswith("if"):
                return
            self.scripts.append(data)

    def feed(self, data):
        self.scripts.clear()
        super().feed(data)
