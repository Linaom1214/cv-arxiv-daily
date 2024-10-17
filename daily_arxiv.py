import os
import re
import json
import arxiv
import yaml
import logging
import argparse
import datetime
import requests

logging.basicConfig(format='[%(asctime)s %(levelname)s] %(message)s',
                    datefmt='%m/%d/%Y %H:%M:%S',
                    level=logging.INFO)

base_url = "https://arxiv.paperswithcode.com/api/v0/papers/"
github_url = "https://api.github.com/search/repositories"
arxiv_url = "http://arxiv.org/"

def load_config(config_file: str) -> dict:
    '''
    config_file: input config file path
    return: a dict of configuration
    '''
    def pretty_filters(**config) -> dict:
        keywords = dict()
        EXCAPE = '\"'
        OR = 'OR'

        def parse_filters(filters: list) -> str:
            ret = ''
            for idx, filter in enumerate(filters):
                ret += (EXCAPE + filter + EXCAPE) if len(filter.split()) > 1 else filter
                if idx != len(filters) - 1:
                    ret += f" {OR} "
            return ret

        for k, v in config['keywords'].items():
            keywords[k] = parse_filters(v['filters'])
        return keywords

    with open(config_file, 'r') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        config['kv'] = pretty_filters(**config)
        logging.info(f'config = {config}')
    return config

def get_authors(authors, first_author=False):
    if not authors:
        return "Unknown"
    return authors[0] if first_author else ", ".join(str(author) for author in authors)

def sort_papers(papers):
    return {k: papers[k] for k in sorted(papers.keys(), reverse=True)}

def get_code_link(qword: str) -> str:
    params = {
        "q": qword,
        "sort": "stars",
        "order": "desc"
    }
    try:
        r = requests.get(github_url, params=params)
        r.raise_for_status()
        results = r.json()
        if results["total_count"] > 0:
            return results["items"][0]["html_url"]
    except Exception as e:
        logging.error(f"Error fetching GitHub link for {qword}: {e}")
    return None

def get_daily_papers(topic, query="slam", max_results=2):
    content, content_to_web = {}, {}
    search_engine = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    for result in search_engine.results():
        try:
            paper_id = result.get_short_id()
            paper_title = result.title
            paper_url = f"{arxiv_url}abs/{paper_id.split('v')[0]}"
            paper_abstract = result.summary.replace("\n", " ")  # 获取摘要并去掉换行符
            paper_first_author = get_authors(result.authors, first_author=True)
            update_time = result.updated.date()

            logging.info(f"Time = {update_time}, title = {paper_title}, author = {paper_first_author}")

            # 尝试获取代码链接
            r = requests.get(base_url + paper_id).json()
            repo_url = r.get("official", {}).get("url", None)

            paper_entry = f"|**{update_time}**|**{paper_title}**|{paper_first_author} et.al.|[{paper_id}]({paper_url})|"
            if repo_url:
                content[paper_id] = paper_entry + f"**[link]({repo_url})**|{paper_abstract}|\n"
                content_to_web[paper_id] = f"- {update_time}, **{paper_title}**, {paper_first_author} et.al., Paper: [{paper_url}], Code: **[{repo_url}]({repo_url})**, Abstract: {paper_abstract}\n"
            else:
                content[paper_id] = paper_entry + f"null|{paper_abstract}|\n"
                content_to_web[paper_id] = f"- {update_time}, **{paper_title}**, {paper_first_author} et.al., Paper: [{paper_url}], Abstract: {paper_abstract}\n"

        except Exception as e:
            logging.error(f"Error processing paper {paper_id}: {e}")

    return {topic: content}, {topic: content_to_web}

def update_paper_links(filename):
    def parse_arxiv_string(s):
        try:
            parts = s.split("|")
            return parts[1].strip(), parts[2].strip(), parts[3].strip(), parts[4].strip(), parts[5].strip(), parts[6].strip()
        except IndexError:
            logging.error(f"Error parsing arxiv string: {s}")
            return None, None, None, None, None, None

    with open(filename, "r") as f:
        content = f.read()
        data = json.loads(content) if content else {}

        for keywords, papers in data.items():
            for paper_id, entry in papers.items():
                update_time, title, authors, paper_url, code_url, abstract = parse_arxiv_string(entry)
                if not code_url or "null" in code_url:
                    try:
                        r = requests.get(base_url + paper_id).json()
                        new_code_url = r.get("official", {}).get("url")
                        if new_code_url:
                            updated_entry = entry.replace("null", f"**[link]({new_code_url})**")
                            data[keywords][paper_id] = updated_entry
                            logging.info(f"Updated {paper_id} with new code link: {new_code_url}")
                    except Exception as e:
                        logging.error(f"Error updating paper {paper_id}: {e}")

    with open(filename, "w") as f:
        json.dump(data, f)

def update_json_file(filename, data_dict):
    """
    更新 JSON 文件的内容。如果文件为空或不合法，使用空字典。
    """
    try:
        # 尝试打开并读取JSON文件
        with open(filename, "r") as f:
            content = f.read().strip()  # 去除多余的空白字符
            if not content:  # 如果文件为空，初始化为空字典
                logging.warning(f"{filename} is empty, initializing with an empty dictionary.")
                json_data = {}
            else:
                json_data = json.loads(content)  # 解析非空文件内容
    except FileNotFoundError:
        logging.warning(f"{filename} not found, creating new JSON file.")
        json_data = {}  # 如果文件不存在，创建一个新的空字典
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {filename}: {e}")
        json_data = {}  # 如果JSON解析失败，使用空字典

    # 更新 JSON 文件内容
    for data in data_dict:
        for keyword, papers in data.items():
            if keyword in json_data:
                json_data[keyword].update(papers)
            else:
                json_data[keyword] = papers

    # 将更新后的内容写回文件
    with open(filename, "w") as f:
        json.dump(json_data, f, indent=4)
    logging.info(f"Updated {filename} with new data.")


def json_to_md(filename, md_filename, task='', to_web=False, use_title=True, show_badge=True):
    """
    @param filename: str, input JSON file path
    @param md_filename: str, output Markdown file path
    """
    DateNow = datetime.date.today().strftime("%Y.%m.%d")

    # 修正读取文件的逻辑，避免直接对空文件进行JSON解析
    with open(filename, "r") as f:
        content = f.read().strip()  # 读取并去除空白字符
        if not content:
            data = {}  # 如果文件为空，设置为一个空字典
        else:
            try:
                data = json.loads(content)  # 尝试解析JSON内容
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding JSON from {filename}: {e}")
                data = {}  # 如果JSON解析失败，使用空字典作为数据

    # 打开Markdown文件准备写入
    with open(md_filename, "w+") as f:
        if use_title and to_web:
            f.write("---\nlayout: default\n---\n\n")
        if show_badge:
            f.write("[![Contributors][contributors-shield]][contributors-url]\n[![Forks][forks-shield]][forks-url]\n")
        f.write(f"## Updated on {DateNow}\n")

        # Markdown表头包含摘要字段
        if use_title:
            f.write("| Publish Date | Title | Authors | PDF | Code | Abstract |\n")
            f.write("|:---------|:-----------------------|:---------|:------|:------|:--------|\n")

        # 遍历数据并写入Markdown格式，确保摘要信息包含在内
        for keyword, papers in data.items():
            sorted_papers = sort_papers(papers)
            for paper in sorted_papers.values():
                f.write(paper)

    logging.info(f"{task} finished")

def demo(**config):
    data_collector = []
    keywords = config['kv']
    max_results = config['max_results']

    for topic, keyword in keywords.items():
        logging.info(f"Fetching papers for topic: {topic}")
        data, data_web = get_daily_papers(topic, query=keyword, max_results=max_results)
        data_collector.append(data)

    json_file = config['json_gitpage_path']
    md_file = config['md_gitpage_path']
    update_json_file(json_file, data_collector)
    json_to_md(json_file, md_file, task="Update GitPage", to_web=True, show_badge=config['show_badge'])

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_path', type=str, default='config.yaml', help='Configuration file path')
    parser.add_argument('--update_paper_links', action='store_true', help='Whether to update paper links')
    args = parser.parse_args()

    config = load_config(args.config_path)
    config['update_paper_links'] = args.update_paper_links
    demo(**config)
