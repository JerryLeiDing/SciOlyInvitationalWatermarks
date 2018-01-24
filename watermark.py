# -*- coding: utf-8 -*-
""" Watermark tests by school for Science Olympiad Invitationals
"""
import argparse
import os
import random
from multiprocessing.dummy import Pool as ThreadPool
from shutil import rmtree
from subprocess import check_call, PIPE, Popen

import matplotlib.pyplot as plt


# Constants and strings
TOURNAMENT_NAME = ""
N_THREADS = 4  # NOTE: Set to about the number of cores for optimal performance
DEF_STAMP_FN = "_overlay.pdf"  # Tmp file location for watermark
PATH_TO_STATIC = "fakepath/"  # NOTE: Fill me in to create htaccess files
HTACCESS_CONFIG = \
"""AuthName "Enter team number and password"
AuthUserFile %s
AuthType Basic
require %s""" % (PATH_TO_STATIC + "%s", "%s") # Set up htaccess
DATA_FILE_HEADER = "TeamNum,Password,Code\n"
DATA_FILE_LINE = "%d,%s,%s\n"


def main():
    """ Main method. Parses command line args"""
    # Argument parser
    parser = argparse.ArgumentParser(description='Watermark a collection of PDFs')
    parser.add_argument(
        'n_teams',
        type=int,
        help="Number of teams (positive integer)",
        metavar='n_teams')
    parser.add_argument(
        'output_directory',
        help='Directory to place output. Generally the year of the tournament',
        metavar='output_directory',
        )
    parser.add_argument(
        '--test_directory',
        default='tests',
        help='Directory which contains PDF files of tests to watermark',
        metavar='test_directory',
        )
    parser.add_argument(
        '--create_htaccess', '-c',
        action='store_true',
        help='Create .htaccess files for Apache access control',
        dest='create_htaccess'
        )
    parser.add_argument(
        '--cached_credentials',
        default=None,
        help='Path to csv of saved credentials',
        metavar='cached_credentials'
    )

    args = parser.parse_args()

    n_teams = args.n_teams
    output_directory = args.output_directory
    test_directory = args.test_directory
    create_htaccess = args.create_htaccess
    cached_credentials = args.cached_credentials
    if cached_credentials != None:
        print "Using cached credentials from file %s" % cached_credentials
        cached_credentials = parse_cached(cached_credentials)
    watermark(n_teams, test_directory, output_directory, create_htaccess,
              cached_credentials)


def watermark(n_teams, test_directory, output_dir, create_htaccess,
              cached_credentials=None):
    """ Main interface for watermarking documents

    Creates team codes, team watermarks, and output directory structure
    Will prompt if file already exists for team codes or output directory exists

    Args:
        n_teams: positive integer number of teams
        test_directory: path to directory holding tests to watermark
        output_dir: path to output directory
        create_htaccess: boolean, True to automatically create .htaccess files
        cached_credentials: Pass a tuple of lists
            'TeamNum','Password','Code'
    """

    # Prompt for deleting directory + team code
    # Create password file randomly
    if os.path.exists(output_dir):
        if raw_input("%s already exists! Delete [Y/n]? " % output_dir) != 'Y':
            exit("Aborted: target directory already exists")
        rmtree(output_dir)
    os.mkdir(output_dir)

    if create_htaccess:
        passwd_file = os.path.join(output_dir, ".htpasswd")
        open(passwd_file, 'w') # Create empty password file
        htaccess_config_n = HTACCESS_CONFIG % (passwd_file, "%s")
        # Deny access by default so .htpasswd is not leaked
        with open(os.path.join(output_dir, ".htaccess"), 'w') as f:
            f.write(htaccess_config_n % " all denied")

    if cached_credentials is None:
        # Create passwords and codes
        teams = xrange(1, n_teams+1)
        passwords = generate_passwords(n_teams)
        codes = generate_codes(n_teams)
    else:
        teams, passwords, codes = cached_credentials

    save_team_information(os.path.join(output_dir, 'team_data.csv'),
                          teams, passwords, codes)

    # Create a subdirectory for every team
    for team in teams:
        os.mkdir(os.path.join(output_dir, str(team)))
        if create_htaccess:
            # Create subfolder htaccess: only that team has access
            with open(os.path.join(output_dir, str(team), '.htaccess'), 'w') as f:
                f.write(htaccess_config_n % ("user " + str(team)))

    # Obtain list of tests to watermark
    tests = []
    for f in os.listdir(test_directory):
        if f.endswith(".pdf") and os.path.isfile(os.path.join(test_directory, f)):
            tests.append(os.path.join(test_directory, f))

    # Apply watermark to all tests for all teams
    for i in xrange(len(teams)):
        print "Watermarking team %d" % (teams[i])
        apply_overlays(tests, teams[i], codes[i], output_dir)
        if create_htaccess:
            # Add password to .htpasswd
            check_call([
                'htpasswd',
                '-b',
                passwd_file,
                str(teams[i]),
                passwords[i]
            ])

    print ""
    print "Created a total of %d documents" % (len(teams) * len(tests))
    print "Watermarked pdfs can be found in %s" % output_dir


def apply_overlays(tests, team, code, target_dir):
    """ Create and apply watermark for all tests for the given team
        Place in the target directory (which must already exist!)

    Args:
        tests: List of filenames of tests to watermark
        team: Integer number of team to watermark
        code: Alphanumeric code of team
        target_dir: Path to the existing directory in which to place output
    """
    # NOTE: Change the main text here
    create_overlay("C-%d" % team, code)
    # Parallelize over multiple threads
    pool = ThreadPool(4)

    def do_watermark(document_file):
        """Helper function to map tasks over thread pool
           Stacks document with watermarkt and rasterizes
        """
        pdftk = Popen([
            "pdftk",
            document_file,
            "multistamp",
            DEF_STAMP_FN,
            "output",
            "-"], stdout=PIPE)
        check_call([
            "convert",
            "-density",
            "150",  # NOTE: This controls quality and output pdf size
            "-",
            "-quality",
            "100",
            os.path.join(
                target_dir,
                str(team),
                os.path.basename(document_file))],
            stdin=pdftk.stdout)
        return 0

    # Watermark each test in a separate job. Close the thread pool afterwards
    pool.map(do_watermark, tests)
    pool.close()
    pool.join()
    # Clean up overlay file
    os.remove(DEF_STAMP_FN)


def create_overlay(main_txt, code, filename=DEF_STAMP_FN):
    """ Create watermark pdf.

    Args:
        main_txt: Main watermark text
        code: code for the given team
        filename: Where to save overlay
    """
    tmp_page_name = ".tmp_overlay.pdf"
    fig, ax = plt.subplots(1, 1, figsize=(8.5, 11))
    ax.set_ylim(0, 1)
    ax.set_xlim(0, 1)

    # NOTE: Change constants here to adjust size, color, and placement of mark
    # Add team-specific code
    ax.text(0.5, 0.05, TOURNAMENT_NAME + " " + code, alpha=0.35, size=12,
            horizontalalignment='center', color='blue')
    # Add main watermark
    ax.text(0.5, 0.5, main_txt, alpha=0.15, size=130,
            horizontalalignment='center', color='black')

    # Clear plot of axes and margins
    ax.set_frame_on(False)
    ax.set_xticks([])
    ax.set_yticks([])
    plt.axis('off')
    fig.subplots_adjust(left=0, right=1.0, top=1.0, bottom=0)
    plt.savefig(
        tmp_page_name,
        format='pdf',
        transparent=True,
        bbox_inches='tight'
    )

    plt.close('all')

    # Stack pages together, throw exception if error
    try:
        check_call(["pdftk", tmp_page_name, "cat", "output", filename])
    finally:
        os.remove(tmp_page_name)


def generate_passwords(n_teams):
    """ Generate a list of n_teams passwords

    Each password has the form 'adjective-noun-NNNN', where N is a digit
    NOTE: requires the presence of "nouns.txt" and "adjectives.txt"
    Only used if create_htaccess is True in `watermark`
    """
    with open('nouns.txt', 'r') as f:
        nouns = f.read().split('\n')
    with open('adjectives.txt', 'r') as f:
        adjs = f.read().split('\n')

    n_nouns = len(nouns)
    n_adjs = len(adjs)

    print "Generating passwords using %d nouns and %d adjectives" % (n_nouns, n_adjs)

    passwords = ["%s-%s-%d" % (random.choice(adjs).strip(),
                               random.choice(nouns).strip(),
                               random.randint(1000, 9999))
                 for _ in xrange(n_teams)]
    return passwords


def generate_codes(n_teams):
    """ Generate a random 8-char alphanumeric code for each team
        This prevents a team from 'framing' another team by
        watermarking their number over the original test"""
    return [''.join(random.choice('1234567890abcdefghijklmnopqrstuvwxyz')
                    for j in xrange(8))
            for _ in xrange(n_teams)]


def parse_cached(cached_credentials):
    """Parse existing csv file

    Requires first 4 columns to be TeamNum, Password, Code, Color [in hex]
    """
    teamnums = []
    passwords = []
    codes = []
    with open(cached_credentials) as f:
        f.readline()
        for line in f:
            tokens = line[:-1].split(',')
            teamnums.append(int(tokens[0]))
            passwords.append(tokens[1])
            codes.append(tokens[2])

    return (teamnums, passwords, codes)


def save_team_information(data_file, teams, passwords, codes):
    """Save team password and data to csv

    Columns are 'TeamNum,Password,Code,Color'
    """
    with open(data_file, 'w') as f:
        # Write header
        f.write(DATA_FILE_HEADER)
        for i, team in enumerate(teams):
            # Append line to data
            f.write(DATA_FILE_LINE % (
                team,
                passwords[i],
                codes[i]
            ))


if __name__ == "__main__":
    main()
