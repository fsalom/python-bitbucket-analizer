# bitbucket_team_analyzer.py
import httpx
import git
import os
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from config import BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD, wage_per_min


def get_repositories():
    url = f"https://api.bitbucket.org/2.0/repositories/rudoapps"
    response = httpx.get(url, auth=(BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD))
    response.raise_for_status()
    repositories = response.json()
    return repositories


def clone_repo(repo_url, repo_name, team):
    repo_dir = os.path.join('repos', team)
    if not os.path.exists(repo_dir):
        os.makedirs(repo_dir)
    repo_path = os.path.join(repo_dir, repo_name)
    if os.path.exists(repo_path):
        repo = git.Repo(repo_path)
        repo.remotes.origin.pull()
    else:
        repo = git.Repo.clone_from(repo_url, repo_path)
    return repo_path


def analyze_commits(repo_path):
    repo = git.Repo(repo_path)
    commits = list(repo.iter_commits('--all'))
    user_stats = defaultdict(lambda: defaultdict(
        lambda: {'added': 0, 'removed': 0, 'commits': 0, 'large_commits': 0, 'bad_messages': 0, 'files_changed': 0,
                 'test_files_changed': 0, 'time_per_line': 0.0}))

    # Determine the start of the current week (Monday)
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())

    # Ensure we include commits from the start of the week until now
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

    for commit in commits:
        commit_date = datetime.fromtimestamp(commit.committed_date)
        if commit_date >= start_of_week:

            author_email = commit.author.email
            date = commit_date.strftime('%Y-%m-%d')
            user_stats[author_email][date]['commits'] += 1

            if "Merge branch" in commit.message or "Merged in" in commit.message or "Merge commit" in commit.message:
                continue

            # Analyzing commit size
            additions = 0
            deletions = 0

            # Iterate over the diffs in the commit
            for diff in commit.diff(commit.parents[0] if commit.parents else None, create_patch=True):
                if diff.a_path and diff.a_path.endswith('project.pbxproj'):
                    continue
                if diff.b_path and diff.b_path.endswith('project.pbxproj'):
                    continue

                diff_text = diff.diff.decode('utf-8')
                for line in diff_text.split('\n'):
                    if line.startswith('+') and not line.startswith('+++') and line[1:].strip():
                        deletions += 1
                    elif line.startswith('-') and not line.startswith('---') and line[1:].strip():
                        additions += 1

            total_lines = additions + deletions
            user_stats[author_email][date]['added'] += additions
            user_stats[author_email][date]['removed'] += deletions

            # Define large commits (example: more than 500 lines changed)
            if total_lines > 500:
                user_stats[author_email][date]['large_commits'] += 1

            # Check for bad commit messages (example: short messages)
            if len(commit.message) < 15:
                user_stats[author_email][date]['bad_messages'] += 1

            # Count files changed
            files_changed = len(commit.stats.files)
            user_stats[author_email][date]['files_changed'] += files_changed

            # Count test files changed
            for file in commit.stats.files.keys():
                if 'test' in file.lower():
                    user_stats[author_email][date]['test_files_changed'] += 1

            # Calculate time per line (assuming 7 hours of work per day)
            if user_stats[author_email][date]['added'] > 0:
                user_stats[author_email][date]['time_per_line'] = (7 * 60) / user_stats[author_email][date]['added']

    return user_stats


if __name__ == "__main__":
    val = input("Enter your git repo: ")
    print(val)

    overall_stats = defaultdict(lambda: defaultdict(
        lambda: {'added': 0, 'removed': 0, 'commits': 0, 'large_commits': 0, 'bad_messages': 0, 'files_changed': 0,
                 'test_files_changed': 0, 'time_per_line': 0.0}))
    repos = get_repositories()

    repo_url = f'https://{BITBUCKET_USERNAME}@bitbucket.org/rudoapps/{val}.git'
    repo_url = repo_url.replace('fer_rudo', f'{BITBUCKET_USERNAME}:{BITBUCKET_APP_PASSWORD}')
    repo_path = clone_repo(repo_url, val, "rudoapps")
    user_stats = analyze_commits(repo_path)

    total_stats = {'added': 0, 'removed': 0, 'commits': 0, 'large_commits': 0, 'bad_messages': 0, 'files_changed': 0,
                   'test_files_changed': 0, 'time_per_line': 0.0}

    with open('user_stats.csv', mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['User', 'Date', 'Commits', 'Lines Added', 'Lines Removed',
                         'Files Changed', 'Test Files Changed', 'Time per Line (min)', 'Cost per Line'])

        for user_email, dates in user_stats.items():
            user_total_added = 0
            user_total_removed = 0
            user_total_commits = 0
            user_total_large_commits = 0
            user_total_bad_messages = 0
            user_total_files_changed = 0
            user_total_test_files_changed = 0
            user_total_time_per_line = 0.0
            print(f"User: {user_email}")
            for date, stats in dates.items():
                user_total_added += stats['added']
                user_total_removed += stats['removed']
                user_total_commits += stats['commits']
                user_total_large_commits += stats['large_commits']
                user_total_bad_messages += stats['bad_messages']
                user_total_files_changed += stats['files_changed']
                user_total_test_files_changed += stats['test_files_changed']
                total_days = datetime.now().weekday() + 1
                if user_total_added > 0: user_total_time_per_line = round((7 * 60 * total_days) / user_total_added, 2)
                user_total_cost_per_line = round(user_total_time_per_line * wage_per_min[user_email], 2)

                writer.writerow(
                    [user_email, date, stats['commits'], stats['added'], stats['removed'], stats['files_changed'],
                     stats['test_files_changed'],
                     stats['time_per_line'], user_total_cost_per_line])
                print(
                    f"  Date: {date}, Commits: {stats['commits']}, Lines Added: {stats['added']}, Lines Removed: {stats['removed']}, Files Changed: {stats['files_changed']}, Test Files Changed: {stats['test_files_changed']}, Time per Line: {stats['time_per_line']} min")

            # Update total stats
            total_stats['added'] += user_total_added
            total_stats['removed'] += user_total_removed
            total_stats['commits'] += user_total_commits
            total_stats['large_commits'] += user_total_large_commits
            total_stats['bad_messages'] += user_total_bad_messages
            total_stats['files_changed'] += user_total_files_changed
            total_stats['test_files_changed'] += user_total_test_files_changed

            print(
                f"Total for {user_email}: Commits: {user_total_commits}, Lines Added: {user_total_added}, Lines Removed: {user_total_removed}, Files Changed: {user_total_files_changed}, Test Files Changed: {user_total_test_files_changed}, {user_total_time_per_line} min/line, {user_total_cost_per_line}€/line\n")

    print("Overall Total for All Users:")
    print(
        f"Total Commits: {total_stats['commits']}, Total Lines Added: {total_stats['added']}, Total Lines Removed: {total_stats['removed']}, Total Files Changed: {total_stats['files_changed']}, Total Test Files Changed: {total_stats['test_files_changed']}")
