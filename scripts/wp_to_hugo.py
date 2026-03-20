#!/usr/bin/env python3
"""Extract WordPress XML export content and generate Hugo markdown files."""

import xml.etree.ElementTree as ET
import re
import os
import html

# Namespaces used in WordPress export
NS = {
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'wp': 'http://wordpress.org/export/1.2/',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'excerpt': 'http://wordpress.org/export/1.2/excerpt/',
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML_FILE = os.path.join(BASE_DIR, 'dcb.WordPress.2026-03-20.xml')


def html_to_markdown(text):
    """Convert HTML content to markdown, stripping WPBakery shortcodes."""
    if not text:
        return ''

    # Remove WPBakery/Visual Composer shortcodes
    text = re.sub(r'\[/?vc_[^\]]*\]', '', text)
    text = re.sub(r'\[/?rev_slider[^\]]*\]', '', text)
    text = re.sub(r'\[/?timeline[^\]]*\]', '', text)
    text = re.sub(r'\[/?envira[^\]]*\]', '', text)
    text = re.sub(r'\[/?contact-form[^\]]*\]', '', text)
    text = re.sub(r'\[/?mk_[^\]]*\]', '', text)
    text = re.sub(r'\[/?et_pb_[^\]]*\]', '', text)

    # Remove WordPress block comments
    text = re.sub(r'<!-- /?wp:\w+[^>]*-->', '', text)

    # Remove span style wrappers (common in WP content)
    text = re.sub(r'<span style="[^"]*">(.*?)</span>', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'<span[^>]*>(.*?)</span>', r'\1', text, flags=re.DOTALL)

    # Convert headings
    text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1', text, flags=re.DOTALL)
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1', text, flags=re.DOTALL)
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1', text, flags=re.DOTALL)
    text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'#### \1', text, flags=re.DOTALL)

    # Convert bold and italic
    text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<em>(.*?)</em>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<i>(.*?)</i>', r'*\1*', text, flags=re.DOTALL)

    # Convert links
    text = re.sub(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL)

    # Convert images
    text = re.sub(r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*/?\s*>', r'![\2](\1)', text)
    text = re.sub(r'<img[^>]*src="([^"]*)"[^>]*/?\s*>', r'![](\1)', text)

    # Convert lists
    text = re.sub(r'<ul[^>]*>', '', text)
    text = re.sub(r'</ul>', '', text)
    text = re.sub(r'<ol[^>]*>', '', text)
    text = re.sub(r'</ol>', '', text)
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1', text, flags=re.DOTALL)

    # Convert blockquotes
    text = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', lambda m: '\n'.join('> ' + line for line in m.group(1).strip().split('\n')), text, flags=re.DOTALL)

    # Convert paragraphs and breaks
    text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<hr\s*/?>', '\n---\n', text)

    # Remove remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode HTML entities
    text = html.unescape(text)

    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = text.strip()

    return text


def get_language(link, slug):
    """Determine language from URL."""
    if '/en/' in link:
        return 'en'
    elif '/de/' in link:
        return 'de'
    else:
        return 'ro'


def escape_yaml(s):
    """Escape a string for YAML frontmatter."""
    if not s:
        return '""'
    # If contains special chars, quote it
    if any(c in s for c in [':', '#', '"', "'", '[', ']', '{', '}', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`']):
        s = s.replace('"', '\\"')
        return f'"{s}"'
    return f'"{s}"'


def parse_xml():
    """Parse WordPress XML and extract published posts and pages."""
    tree = ET.parse(XML_FILE)
    root = tree.getroot()
    channel = root.find('channel')

    posts = []
    pages = []

    for item in channel.findall('item'):
        post_type = item.find('wp:post_type', NS)
        status = item.find('wp:status', NS)

        if post_type is None or status is None:
            continue
        if status.text != 'publish':
            continue
        if post_type.text not in ('post', 'page'):
            continue

        title = item.find('title').text or ''
        slug = item.find('wp:post_name', NS).text or ''
        link = item.find('link').text or ''
        date = item.find('wp:post_date', NS).text or ''
        author = item.find('dc:creator', NS).text or ''
        content_el = item.find('content:encoded', NS)
        content = content_el.text if content_el is not None and content_el.text else ''

        # Get categories
        categories = []
        for cat in item.findall('category'):
            domain = cat.get('domain', '')
            if domain == 'category' and cat.text:
                cat_name = cat.text
                if cat_name not in ('Uncategorized', 'Fără categorie', 'Fara categorie'):
                    categories.append(cat_name)

        lang = get_language(link, slug)

        entry = {
            'title': title,
            'slug': slug,
            'link': link,
            'date': date,
            'author': author,
            'content': content,
            'categories': categories,
            'lang': lang,
            'type': post_type.text,
        }

        if post_type.text == 'post':
            posts.append(entry)
        else:
            pages.append(entry)

    return posts, pages


def lang_dir(lang):
    """Map language code to content directory name."""
    return {'en': 'english', 'ro': 'romanian', 'de': 'german'}[lang]


def write_blog_post(post):
    """Write a single blog post as Hugo markdown."""
    lang = post['lang']
    slug = post['slug']
    content = html_to_markdown(post['content'])
    date = post['date'][:10] if post['date'] else '2024-01-01'

    cats = post['categories'] if post['categories'] else ['Articles' if lang == 'en' else 'Artikel' if lang == 'de' else 'Articole']
    cats_yaml = '[' + ', '.join(f'"{c}"' for c in cats) + ']'

    dir_path = os.path.join(BASE_DIR, 'content', lang_dir(lang), 'blog')
    os.makedirs(dir_path, exist_ok=True)

    filepath = os.path.join(dir_path, f'{slug}.md')

    title = post['title'].replace('"', '\\"')

    frontmatter = f'''---
title: "{title}"
date: {date}
draft: false
categories: {cats_yaml}
---

'''

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(frontmatter + content + '\n')

    print(f'  Created: content/{lang_dir(lang)}/blog/{slug}.md')


def main():
    posts, pages = parse_xml()

    print(f'Found {len(posts)} published posts, {len(pages)} published pages')

    # Count by language
    for lang in ('ro', 'en', 'de'):
        p = [x for x in posts if x['lang'] == lang]
        pg = [x for x in pages if x['lang'] == lang]
        print(f'  {lang}: {len(p)} posts, {len(pg)} pages')

    # Write blog posts
    print('\nCreating blog posts...')
    for post in posts:
        write_blog_post(post)

    # Print page slugs for reference
    print('\nPages by language (for manual content update):')
    for lang in ('en', 'ro', 'de'):
        print(f'\n  {lang.upper()} pages:')
        for page in sorted([p for p in pages if p['lang'] == lang], key=lambda x: x['slug']):
            content_preview = html_to_markdown(page['content'])[:80].replace('\n', ' ')
            print(f'    {page["slug"]}: {content_preview}...')

    # Export page content for use
    print('\n\nExporting page content...')
    for page in pages:
        lang = page['lang']
        slug = page['slug']
        content = html_to_markdown(page['content'])
        out_dir = os.path.join(BASE_DIR, 'scripts', 'extracted_pages', lang)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f'{slug}.txt'), 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'  Exported: scripts/extracted_pages/{lang}/{slug}.txt')


if __name__ == '__main__':
    main()
