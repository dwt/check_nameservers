#!/usr/bin/env python
# encoding: utf-8

"""
Checks that all advertised nameservers for a domain are on the same soa version,
thus ensuring your customers will get consistent answers to their dns queries.
Will return the standard Icinga error codes.
See: https://www.monitoring-plugins.org/doc/guidelines.html#AEN78

Usage:
    check_nameservers_are_in_sync_for_zone.py --domain=DOMAIN [--warning=WARNING_NAMESERVER_LIMIT]
        [--critical=CRITICAL_NAMESERVER_LIMIT] [--hidden-primary=NAMESERVER...]
    check_nameservers_are_in_sync_for_zone.py --selftest [<unittest-options>...]

Option:
    -h, --help              Show this screen and exit.
    -d, --domain DOMAIN     The domain to check.
    -w, --warning WARNING_NAMESERVER_LIMIT      Warn if less nameservers [default: 2]
    -c, --critical CRITICAL_NAMESERVER_LIMIT    Critical if less nameservers [default: 1]
    --hidden-primary NAMESERVER...    List of hidden primaries [default: ()]
    --selftest              Execute the unittests for this module

Copyright: Martin Häcker <spamfenger (at) gmx.de>
License AGPL: https://www.gnu.org/licenses/agpl-3.0.html
"""

"""
Maintained at: https://github.com/dwt/monitoring_probes

TODO
* add suppport for ipv4 and ipv6 checks as these might be different nameservers
* allow disabling ipv6 checks
* ensure dig calls skip all caches
* collect all IP addresses for nameservers that resolve to multiple IPs and check them directly
* still provide names in error messages
"""

def main():
    arguments = docopt(__doc__)
    if arguments['--selftest']:
        unittest.main(argv=sys.argv[1:])
    
    (return_code, label), message \
        = check_soas_equal_for_domain(
            domain_name=arguments['--domain'],
            warning_minimum_nameservers=int(arguments['--warning']),
            critical_minimum_nameservers=int(arguments['--critical']),
            hidden_primaries=arguments['--hidden-primary'],
    )
    print("%s: %s" % (label, message))
    sys.exit(return_code)

from docopt import docopt  # Only external requirement. Install via: pip install docopt

import sys
import subprocess
from StringIO import StringIO
# import logging

def check_output(command):
    "Stub for subprocess.check_output which is only available from python 2.7+"
    buffer_ = StringIO()
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    for line in process.stdout:
        buffer_.write(line)
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command)
    return buffer_.getvalue()

class NAGIOS(object):
    OK = (0, 'OK')
    WARNING = (1, 'WARNING')
    CRITICAL = (2, 'CRITICAL')
    UNKNOWN = (3, 'UNKNOWN')

def nameservers_for_domain(domain_name):
    output = check_output(['dig', '+short', 'NS', domain_name])
    if "" == output: return []
    return map(lambda each: each.rstrip('.'), output.strip().split('\n'))

def soa_for_domain_with_dns_server(domain_name, dns_server_name):
    try:
        output = check_output(['dig', '+short', 'SOA', domain_name, '@' + dns_server_name])
        return output.strip()
    except subprocess.CalledProcessError as error:
        # TODO if --verbose
        #logging.exception('soa_for_domain_with_dns_server(domain_name=%r, dns_server_name=%r)', domain_name, dns_server_name)
        return ''

def check_soas_equal_for_domain(domain_name, warning_minimum_nameservers=2, critical_minimum_nameservers=1, hidden_primaries=()):
    # hidden primaries can't count towards the limits
    try:
        nameservers = nameservers_for_domain(domain_name)
        if len(nameservers) == 0:
            return (NAGIOS.CRITICAL, 'No nameserver for domain "%s", dns is unavailable.' % domain_name)
        
        all_nameservers = nameservers + list(hidden_primaries)
        soa_records = map(lambda each: soa_for_domain_with_dns_server(domain_name, each), all_nameservers)
        empty_response_servers = [all_nameservers[index] for index, record in enumerate(soa_records) if 0 == len(record)]
        if len(empty_response_servers) >= 1:
            return (NAGIOS.CRITICAL,
                'Nameserver(s) %s did not return SOA record for domain "%s"' % (empty_response_servers, domain_name))
        are_all_soas_equal = all(map(lambda each: each == soa_records[0], soa_records))
    except Exception as error:
        # TODO if --verbose
        # logging.exception('check_soas_equal_for_domain(domain_name=%r, warning_minimum_nameservers=%r, critical_minimum_nameservers=%r, hidden_primaries=%r)', domain_name, warning_minimum_nameservers, critical_minimum_nameservers, hidden_primaries)
        return (NAGIOS.WARNING, "%r" % error)
    
    if not are_all_soas_equal:
        return (NAGIOS.CRITICAL, 'Nameservers do not agree for domain "%s" %r' % (domain_name, soa_records))
    elif len(nameservers) < critical_minimum_nameservers:
        return (NAGIOS.CRITICAL, 'Less than %d nameservers for domain "%s", only %d available. %s' % (
            critical_minimum_nameservers, domain_name, len(nameservers), nameservers))
    elif len(nameservers) < warning_minimum_nameservers:
        return (NAGIOS.WARNING, 'Expected at least %d nameservers for domain "%s", but only found %d - %r' % (
            warning_minimum_nameservers, domain_name, len(nameservers), nameservers))
    else:  # are_all_soas_equal
        return (NAGIOS.OK, soa_records[0])
    

import unittest

def expect(*args, **kwargs):
    from pyexpect import expect as expect_
    return expect_(*args, **kwargs)

# REFACT add / change tests to go through the shell interface, to ensure the wiring is correct
class SOATest(unittest.TestCase):
    
    def setUp(self):
        self._stubbed_commands = dict()
        global check_output
        self._original_check_output = check_output
        check_output = self.check_output_mock
        
    def tearDown(self):
        global check_output
        check_output = self._original_check_output
    
    def check_output_mock(self, command):
        normalized_command = ' '.join(command)
        assert normalized_command in self._stubbed_commands, \
            "Missing output for <%s>, only have output for <%s>" % (normalized_command, self._stubbed_commands)
        import inspect
        if inspect.isfunction(self._stubbed_commands[normalized_command]):
            return self._stubbed_commands[normalized_command]()
        return self._stubbed_commands[normalized_command]
    
    def on_command(self, expected_command):
        "Expects command as one string"
        self._expected_command = expected_command
        return self
    
    def provide_output(self, stubbed_output):
        "Outdents output"
        output = '\n'.join(map(lambda each: each.lstrip(), stubbed_output.split('\n')))
        self._stubbed_commands[self._expected_command] = output
        del self._expected_command
    
    def provide_function(self, a_function):
        self._stubbed_commands[self._expected_command] = a_function
        del self._expected_command
    
    ## Tests
    
    def test_get_nameservers_for_domain(self):
        self.on_command('dig +short NS yeepa.de').provide_output("""\
            nsc1.schlundtech.de.
            nsb1.schlundtech.de
            nsa1.schlundtech.de.
            nsd1.schlundtech.de.""")
        nameservers = nameservers_for_domain('yeepa.de')
        expect(nameservers) == [
            'nsc1.schlundtech.de',
            'nsb1.schlundtech.de',
            'nsa1.schlundtech.de',
            'nsd1.schlundtech.de']
    
    def test_get_soa_for_domain_from_nameserver(self):
        self.on_command('dig +short SOA yeepa.de @nsc1.schlundtech.de').provide_output("""\
            nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600""")
        soa = soa_for_domain_with_dns_server('yeepa.de', 'nsc1.schlundtech.de')
        expect(soa) == 'nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600'
    
    def test_should_compare_soas_from_all_web_servers(self):
        self.on_command('dig +short NS yeepa.de').provide_output("""\
            nsc1.schlundtech.de.
            nsb1.schlundtech.de.""")
        self.on_command('dig +short SOA yeepa.de @nsc1.schlundtech.de').provide_output("""\
            nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600""")
        self.on_command('dig +short SOA yeepa.de @nsb1.schlundtech.de').provide_output("""\
            nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600""")
        expect(check_soas_equal_for_domain('yeepa.de')) == (
            NAGIOS.OK, 'nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600')
    
    def test_should_compare_hidden_primaries(self):
        self.on_command('dig +short NS yeepa.de').provide_output("""\
            nsc1.schlundtech.de.
            nsb1.schlundtech.de.""")
        self.on_command('dig +short SOA yeepa.de @nsc1.schlundtech.de').provide_output("""\
            nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600""")
        self.on_command('dig +short SOA yeepa.de @nsb1.schlundtech.de').provide_output("""\
            nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600""")
        # hidden primary query
        self.on_command('dig +short SOA yeepa.de @zhref-mail.zms.hosting').provide_output("""\
            nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600""")
        
        expect(check_soas_equal_for_domain('yeepa.de', hidden_primaries=['zhref-mail.zms.hosting'])) == (
            NAGIOS.OK, 'nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600')
    
    def test_should_show_critical_error_if_hidden_primary_is_dead(self):
        self.on_command('dig +short NS yeepa.de').provide_output("""\
            nsc1.schlundtech.de.
            nsb1.schlundtech.de.""")
        self.on_command('dig +short SOA yeepa.de @nsc1.schlundtech.de').provide_output("""\
            nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600""")
        self.on_command('dig +short SOA yeepa.de @nsb1.schlundtech.de').provide_output("""\
            nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600""")
        # hidden primary query
        def fail(): raise subprocess.CalledProcessError(-1, 'dig ...', "Process error'd")
        self.on_command('dig +short SOA yeepa.de @zhref-mail.zms.hosting').provide_function(fail)
        
        expect(check_soas_equal_for_domain('yeepa.de', hidden_primaries=['zhref-mail.zms.hosting'])) == (
            NAGIOS.CRITICAL, 'Nameserver(s) [\'zhref-mail.zms.hosting\'] did not return SOA record for domain "yeepa.de"')
    
    def test_should_return_false_if_soas_differ(self):
        self.on_command('dig +short NS yeepa.de').provide_output("""\
            nsc1.schlundtech.de.
            nsb1.schlundtech.de.""")
        self.on_command('dig +short SOA yeepa.de @nsc1.schlundtech.de').provide_output("not equal")
        self.on_command('dig +short SOA yeepa.de @nsb1.schlundtech.de').provide_output("to this")
        expect(check_soas_equal_for_domain('yeepa.de')) == (NAGIOS.CRITICAL, 'Nameservers do not agree for domain "yeepa.de" [\'not equal\', \'to this\']')
    
    def test_should_erorr_if_nameservers_are_not_authoritative(self):
        self.on_command('dig +short NS example.com').provide_output("""\
            b.iana-servers.net.
            a.iana-servers.net.""")
        self.on_command('dig +short SOA example.com @a.iana-servers.net').provide_output("anything")
        self.on_command('dig +short SOA example.com @b.iana-servers.net').provide_output("")
        expect(check_soas_equal_for_domain('example.com')) == (NAGIOS.CRITICAL, 'Nameserver(s) [\'b.iana-servers.net\'] did not return SOA record for domain "example.com"')
    
    def test_should_error_if_no_nameservers(self):
        self.on_command('dig +short NS yeepa.de').provide_output("")
        expect(check_soas_equal_for_domain('yeepa.de')) \
             == (NAGIOS.CRITICAL, 'No nameserver for domain "yeepa.de", dns is unavailable.')
    
    def test_should_allow_to_configure_warning_level_for_number_of_nameservers(self):
        self.on_command('dig +short NS yeepa.de').provide_output("""\
            nsc1.schlundtech.de.
            nsb1.schlundtech.de.""")
        self.on_command('dig +short SOA yeepa.de @nsc1.schlundtech.de').provide_output("equal")
        self.on_command('dig +short SOA yeepa.de @nsb1.schlundtech.de').provide_output("equal")
        expect(check_soas_equal_for_domain('yeepa.de', warning_minimum_nameservers=3)) \
             == (NAGIOS.WARNING, 'Expected at least 3 nameservers for domain "yeepa.de", but only found 2 - '
                 "['nsc1.schlundtech.de', 'nsb1.schlundtech.de']")
    
    def test_should_error_if_less_than_critical_nameservers(self):
        self.on_command('dig +short NS yeepa.de').provide_output("""nsc1.schlundtech.de.""")
        self.on_command('dig +short SOA yeepa.de @nsc1.schlundtech.de').provide_output("good enough")
        expect(check_soas_equal_for_domain('yeepa.de', critical_minimum_nameservers=2)) \
             == (NAGIOS.CRITICAL, 'Less than 2 nameservers for domain "yeepa.de", only 1 available. [\'nsc1.schlundtech.de\']')
    
    def test_should_catch_unexpected_errors(self):
        global check_output
        def fail(*args): raise AssertionError('fnord')
        check_output     = fail
        expect(check_soas_equal_for_domain('yeepa.de')) \
             == (NAGIOS.WARNING, "AssertionError('fnord',)")
    
    def test_should_count_non_answering_nameserver_as_empty_response(self):
        self.on_command('dig +short NS yeepa.de').provide_output("""\
            nsc1.schlundtech.de.
            nsb1.schlundtech.de.""")
        self.on_command('dig +short SOA yeepa.de @nsc1.schlundtech.de').provide_output("""\
            nsa1.schlundtech.de. sh.sntl-publishing.com. 2014090302 43200 7200 1209600 600""")
        def fail(): raise subprocess.CalledProcessError(-1, 'dig ...', "process error'd")
        self.on_command('dig +short SOA yeepa.de @nsb1.schlundtech.de').provide_function(fail)
        expect(check_soas_equal_for_domain('yeepa.de', )) == (
            NAGIOS.CRITICAL, 'Nameserver(s) [\'nsb1.schlundtech.de\'] did not return SOA record for domain "yeepa.de"')

if __name__ == '__main__':
    main()
