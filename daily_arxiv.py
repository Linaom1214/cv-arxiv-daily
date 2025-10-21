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

github_url = "https://api.github.com/search/repositories"
arxiv_url = "http://arxiv.org/"

def load_config(config_file: str) -> dict:
    """加载配置文件并格式化关键词"""
    def pretty_filters(**config) -> dict:
        keywords = dict()
        EXCAPE = '\"'
        OR = ' OR '

        def parse_filters(filters: list):
            ret = ''
            for idx, filter in enumerate(filters):
                if len(filter.split()) > 1:
                    ret += (EXCAPE + filter + EXCAPE)
                else:
                    ret += filter
                if idx != len(filters) - 1:
                    ret += OR
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
    if first_author:
        return authors[0]
    return ", ".join(str(author) for author in authors)


def sort_papers(papers):
    return dict(sorted(papers.items(), reverse=True))


def get_code_link(query_word: str) -> str:
    """使用 GitHub API 根据论文标题或关键词查找相关代码"""
    params = {"q": query_word, "sort": "stars", "order": "desc"}
    r = requests.get(github_url, params=params)
    results = r.json()
    if results.get("total_count", 0) > 0:
        return results["items"][0]["html_url"]
    return None


def get_daily_papers(topic, query="slam", max_results=2):
    """从 arXiv 获取最新论文，并通过 GitHub 搜索代码"""
    content = dict()
    content_to_web = dict()
    search_engine = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    for result in search_engine.results():
        paper_id = result.get_short_id()
        paper_title = result.title
        paper_url = arxiv_url + 'abs/' + paper_id
        paper_abstract = result.summary.replace("\n", " ")
        paper_authors = get_authors(result.authors)
        paper_first_author = get_authors(result.authors, first_author=True)
        update_time = result.updated.date()

        logging.info(f"Time = {update_time}, title = {paper_title}")

        try:
            # 搜索 GitHub 代码仓库
            repo_url = get_code_link(paper_title)
            if repo_url:
                content[paper_id] = f"|**{update_time}**|**{paper_title}**|{paper_first_author} et.al.|[link]({paper_url})|**[code]({repo_url})**|\n"
                content_to_web[paper_id] = f"- {update_time}, **{paper_title}**, {paper_first_author} et.al., Paper: [{paper_url}]({paper_url}), Code: **[{repo_url}]({repo_url})**\n"
            else:
                content[paper_id] = f"|**{update_time}**|**{paper_title}**|{paper_first_author} et.al.|[link]({paper_url})|null|\n"
                content_to_web[paper_id] = f"- {update_time}, **{paper_title}**, {paper_first_author} et.al., Paper: [{paper_url}]({paper_url})\n"

        except Exception as e:
            logging.error(f"Exception: {e} for paper {paper_id}")

    return {topic: content}, {topic: content_to_web}


def update_json_file(filename, data_dict):
    """更新 JSON 数据文件"""
    if os.path.exists(filename):
        with open(filename, "r") as f:
            content = f.read()
            m = json.loads(content) if content else {}
    else:
        m = {}

    json_data = m.copy()

    for data in data_dict:
        for keyword, papers in data.items():
            json_data.setdefault(keyword, {}).update(papers)

    with open(filename, "w") as f:
        json.dump(json_data, f, indent=2)


def json_to_md(filename, md_filename, task='', to_web=False):
    """将 JSON 转换为 Markdown"""
    DateNow = str(datetime.date.today()).replace('-', '.')

    with open(filename, "r") as f:
        content = f.read()
        data = json.loads(content) if content else {}

    with open(md_filename, "w") as f:
        f.write(f"## Updated on {DateNow}\n\n")

        for keyword, day_content in data.items():
            if not day_content:
                continue
            f.write(f"### {keyword}\n\n")
            f.write("| Date | Title | Authors | Paper | Code |\n")
            f.write("|------|--------|---------|--------|--------|\n")

            for _, v in sort_papers(day_content).items():
                f.write(v)
            f.write("\n")

    logging.info(f"{task} finished")


def demo(**config):
    data_collector = []
    data_collector_web = []

    keywords = config['kv']
    max_results = config['max_results']

    logging.info(f"Fetching papers...")
    for topic, keyword in keywords.items():
        data, data_web = get_daily_papers(topic, query=keyword, max_results=max_results)
        data_collector.append(data)
        data_collector_web.append(data_web)

    # 更新本地 JSON 与 Markdown
    json_file = config['json_readme_path']
    md_file = config['md_readme_path']

    update_json_file(json_file, data_collector)
    json_to_md(json_file, md_file, task='Update Readme')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_path', type=str, default='config.yaml',
                        help='configuration file path')
    args = parser.parse_args()
    config = load_config(args.config_path)
    demo(**config)
