#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json

import pytest
from selenium.webdriver.support.event_firing_webdriver import EventFiringWebDriver
from selenium.webdriver.common.proxy import Proxy
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium import selenium
from selenium import webdriver


class Client(object):

    def __init__(self, test_id, options):
        self.test_id = test_id
        self.host = options.host
        self.port = options.port
        self.base_url = options.base_url
        self.api = options.api.upper()

        self.webdriver = self.api == 'WEBDRIVER'
        self.rc = self.api == 'RC'

        if self.webdriver:
            self.driver = options.driver
            self.capabilities = options.capabilities
            self.chrome_path = options.chrome_path
            self.chrome_options = options.chrome_options or '{}'
            self.firefox_path = options.firefox_path
            self.firefox_preferences = options.firefox_preferences
            self.profile_path = options.profile_path
            self.extension_paths = options.extension_paths or []
            self.opera_path = options.opera_path
            self.timeout = options.webqatimeout

            if self.driver.upper() == 'REMOTE':
                self.browser_name = options.browser_name
                self.browser_version = options.browser_version
                self.platform = options.platform

            if options.event_listener:
                mod_name, class_name = options.event_listener.rsplit('.', 1)
                mod = __import__(mod_name, fromlist=[class_name])
                self.event_listener = getattr(mod, class_name)
            else:
                self.event_listener = None

        if self.rc:
            self.browser = options.environment or options.browser
            self.timeout = options.webqatimeout * 1000

        self.capture_network = options.capture_network
        self.default_implicit_wait = 10
        self.sauce_labs_credentials = options.sauce_labs_credentials_file
        self.assume_untrusted = options.assume_untrusted
        self.proxy_host = options.proxy_host
        self.proxy_port = options.proxy_port

    def check_usage(self):
        self.check_basic_usage()

        if self.webdriver:
            self.check_webdriver_usage()
        else:
            self.check_rc_usage()

    def check_basic_usage(self):
        if not self.base_url:
            raise pytest.UsageError('--baseurl must be specified.')

    def check_webdriver_usage(self):
        if self.driver.upper() == 'REMOTE':
            if not self.browser_name:
                raise pytest.UsageError("--browsername must be specified when using the 'webdriver' api.")

            if not self.platform:
                raise pytest.UsageError("--platform must be specified when using the 'webdriver' api.")

    def check_rc_usage(self):
        if not self.browser:
            raise pytest.UsageError("--browser or --environment must be specified when using the 'rc' api.")

    def start(self):
        self.check_usage()
        if self.webdriver:
            self.start_webdriver_client()
            self.selenium.implicitly_wait(self.default_implicit_wait)
        else:
            self.start_rc_client()
            self.selenium.set_timeout(self.timeout)
            self.selenium.set_context(self.test_id)

    def start_webdriver_client(self):
        capabilities = {}
        if self.capabilities:
            capabilities.update(json.loads(self.capabilities))
        if self.proxy_host and self.proxy_port:
            proxy = Proxy()
            proxy.http_proxy = '%s:%s' % (self.proxy_host, self.proxy_port)
            proxy.ssl_proxy = proxy.http_proxy
            proxy.add_to_capabilities(capabilities)
        profile = None

        if self.driver.upper() == 'REMOTE':
            capabilities.update(getattr(webdriver.DesiredCapabilities, self.browser_name.upper()))
            if json.loads(self.chrome_options) or self.extension_paths:
                capabilities = self.create_chrome_options(
                    self.chrome_options,
                    self.extension_paths).to_capabilities()
            if self.browser_name.upper() == 'FIREFOX':
                profile = self.create_firefox_profile(
                    self.firefox_preferences,
                    self.profile_path,
                    self.extension_paths)
            if self.browser_version:
                capabilities['version'] = self.browser_version
            capabilities['platform'] = self.platform.upper()
            executor = 'http://%s:%s/wd/hub' % (self.host, self.port)
            try:
                self.selenium = webdriver.Remote(command_executor=executor,
                                                 desired_capabilities=capabilities or None,
                                                 browser_profile=profile)
            except AttributeError:
                valid_browsers = [attr for attr in dir(webdriver.DesiredCapabilities) if not attr.startswith('__')]
                raise AttributeError("Invalid browser name: '%s'. Valid options are: %s" % (self.browser_name, ', '.join(valid_browsers)))

        elif self.driver.upper() == 'CHROME':
            options = None
            if self.chrome_options or self.extension_paths:
                options = self.create_chrome_options(
                    self.chrome_options,
                    self.extension_paths)
            if self.chrome_path:
                self.selenium = webdriver.Chrome(executable_path=self.chrome_path,
                                                 chrome_options=options,
                                                 desired_capabilities=capabilities or None)
            else:
                self.selenium = webdriver.Chrome(chrome_options=options,
                                                 desired_capabilities=capabilities or None)

        elif self.driver.upper() == 'FIREFOX':
            binary = self.firefox_path and FirefoxBinary(self.firefox_path) or None
            profile = self.create_firefox_profile(
                self.firefox_preferences,
                self.profile_path,
                self.extension_paths)
            self.selenium = webdriver.Firefox(
                firefox_binary=binary,
                firefox_profile=profile,
                capabilities=capabilities or None)
        elif self.driver.upper() == 'IE':
            self.selenium = webdriver.Ie()
        elif self.driver.upper() == 'OPERA':
            capabilities.update(webdriver.DesiredCapabilities.OPERA)
            self.selenium = webdriver.Opera(executable_path=self.opera_path,
                                            desired_capabilities=capabilities)
        else:
            self.selenium = getattr(webdriver, self.driver)()

        if self.event_listener is not None and not isinstance(self.selenium, EventFiringWebDriver):
            self.selenium = EventFiringWebDriver(self.selenium, self.event_listener())

    def start_rc_client(self):
        self.selenium = selenium(self.host, str(self.port), self.browser, self.base_url)

        if self.capture_network:
            self.selenium.start('captureNetworkTraffic=true')
        else:
            self.selenium.start()

    @property
    def session_id(self):
        if self.webdriver:
            return self.selenium.session_id
        else:
            return self.selenium.get_eval('selenium.sessionId')

    def create_firefox_profile(self, preferences, profile_path, extensions):
        profile = webdriver.FirefoxProfile(profile_path)
        if preferences:
            [profile.set_preference(k, v) for k, v in json.loads(preferences).items()]
        profile.assume_untrusted_cert_issuer = self.assume_untrusted
        profile.update_preferences()
        for extension in extensions:
            profile.add_extension(extension)
        return profile

    def create_chrome_options(self, preferences, extensions):
        options = webdriver.ChromeOptions()
        options_from_json = json.loads(preferences)

        if 'arguments' in options_from_json:
            for args_ in options_from_json['arguments']:
                options.add_argument(args_)

        if 'binary_location' in options_from_json:
            options.binary_location = options_from_json['binary_location']

        for extension in extensions:
            options.add_extension(extension)

        return options

    @property
    def screenshot(self):
        try:
            if self.webdriver:
                screenshot = self.selenium.get_screenshot_as_base64()
            else:
                screenshot = self.selenium.capture_entire_page_screenshot_to_string('')
            return screenshot
        except:
            return None

    @property
    def html(self):
        try:
            if self.webdriver:
                html = self.selenium.page_source
            else:
                html = self.selenium.get_html_source()
            return html.encode('utf-8')
        except:
            return None

    @property
    def log(self):
        try:
            if self.rc:
                return self.selenium.get_log().encode('utf-8')
        except:
            return None

    @property
    def network_traffic(self):
        try:
            if self.rc and self.capture_network:
                return self.selenium.captureNetworkTraffic('json')
        except:
            return None

    @property
    def url(self):
        try:
            if self.webdriver:
                url = self.selenium.current_url
            else:
                url = self.selenium.get_location()
            return url
        except:
            return None

    def stop(self):
        try:
            if self.webdriver:
                self.selenium.quit()
            else:
                self.selenium.stop()
        except:
            pass
