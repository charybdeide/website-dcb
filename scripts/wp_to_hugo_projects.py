#!/usr/bin/env python3
"""Extract WordPress te_announcements (projects) and generate Hugo markdown files."""

import xml.etree.ElementTree as ET
import re
import os
import html
import urllib.request
from datetime import datetime

# Reuse from wp_to_hugo.py
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wp_to_hugo import html_to_markdown, escape_yaml

NS = {
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'wp': 'http://wordpress.org/export/1.2/',
    'dc': 'http://purl.org/dc/elements/1.1/',
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML_FILE = os.path.join(BASE_DIR, 'dcb.WordPress.2026-03-20.xml')


def lang_dir(lang):
    return {'en': 'english', 'ro': 'romanian', 'de': 'german'}[lang]


def parse_gallery_data(serialized):
    """Extract image URLs from PHP-serialized Envira gallery data."""
    urls = []
    # Match src fields in PHP serialized data: "src";s:123:"https://..."
    for m in re.finditer(r'"src";s:\d+:"([^"]+)"', serialized):
        url = m.group(1)
        if url and ('wp-content' in url or 'uploads' in url):
            urls.append(url)
    return urls


def download_image(url, local_path):
    """Download an image if it doesn't already exist."""
    if os.path.exists(local_path):
        return True
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    # Try both domains
    urls_to_try = [url]
    if 'diasporacivica.com' in url:
        urls_to_try.append(url.replace('diasporacivica.com', 'diasporacivica.berlin'))
    elif 'diasporacivica.berlin' in url:
        urls_to_try.append(url.replace('diasporacivica.berlin', 'diasporacivica.com'))

    for try_url in urls_to_try:
        try:
            req = urllib.request.Request(try_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(local_path, 'wb') as f:
                    f.write(resp.read())
            return True
        except Exception:
            continue
    return False


def main():
    tree = ET.parse(XML_FILE)
    root = tree.getroot()
    channel = root.find('channel')

    # Build attachment map: post_id -> URL
    att_map = {}
    for item in channel.findall('item'):
        pt = item.find('wp:post_type', NS)
        pid = item.find('wp:post_id', NS)
        if pt is not None and pt.text == 'attachment' and pid is not None:
            url_el = item.find('wp:attachment_url', NS)
            if url_el is not None and url_el.text:
                att_map[pid.text] = url_el.text

    # Build gallery map: gallery post_id -> list of image URLs
    gallery_map = {}
    gallery_slug_map = {}
    for item in channel.findall('item'):
        pt = item.find('wp:post_type', NS)
        if pt is None or pt.text != 'envira':
            continue
        pid = item.find('wp:post_id', NS).text
        slug = item.find('wp:post_name', NS).text or pid

        for meta in item.findall('wp:postmeta', NS):
            key = meta.find('wp:meta_key', NS)
            val = meta.find('wp:meta_value', NS)
            if key is not None and key.text == '_eg_gallery_data' and val is not None and val.text:
                urls = parse_gallery_data(val.text)
                if urls:
                    gallery_map[pid] = {'slug': slug, 'urls': urls}
                    gallery_slug_map[slug] = {'id': pid, 'urls': urls}

    print(f"Found {len(gallery_map)} Envira galleries with images")

    # Extract te_announcements (projects)
    projects = []
    for item in channel.findall('item'):
        pt = item.find('wp:post_type', NS)
        status = item.find('wp:status', NS)
        if pt is None or pt.text != 'te_announcements' or status is None or status.text != 'publish':
            continue

        title = item.find('title').text or ''
        slug = item.find('wp:post_name', NS).text or ''
        link = item.find('link').text or ''
        content_el = item.find('content:encoded', NS)
        content = content_el.text if content_el is not None and content_el.text else ''

        # Detect language from Polylang taxonomy
        lang = 'ro'
        for cat in item.findall('category'):
            if cat.get('domain') == 'language':
                lc = cat.get('nicename', '')
                if lc in ('en', 'de'):
                    lang = lc

        # Get metadata
        event_date = None
        thumb_url = None
        for meta in item.findall('wp:postmeta', NS):
            key = meta.find('wp:meta_key', NS)
            val = meta.find('wp:meta_value', NS)
            if key is None or val is None or not val.text:
                continue
            if key.text == 'announcement_date':
                try:
                    event_date = datetime.fromtimestamp(int(val.text)).strftime('%Y-%m-%d')
                except (ValueError, OSError):
                    pass
            elif key.text == '_thumbnail_id':
                thumb_url = att_map.get(val.text)

        if not event_date:
            # Fallback to post date
            pd = item.find('wp:post_date', NS)
            event_date = pd.text[:10] if pd is not None and pd.text else '2020-01-01'

        # Resolve Envira galleries in content
        gallery_images = []
        gallery_ids = re.findall(r'\[envira-gallery\s+id="(\d+)"\]', content)
        gallery_slugs = re.findall(r'\[envira-gallery\s+slug="([^"]+)"\]', content)

        for gid in gallery_ids:
            if gid in gallery_map:
                gallery_images.extend(gallery_map[gid]['urls'])

        for gslug in gallery_slugs:
            if gslug in gallery_slug_map:
                gallery_images.extend(gallery_slug_map[gslug]['urls'])

        # Extract first embedded image as featured image if no thumbnail
        featured_image = None
        if thumb_url:
            featured_image = thumb_url
        else:
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
            if img_match:
                img_url = img_match.group(1)
                # Skip tiny images (emojis, tracking pixels)
                if 'emoji' not in img_url and 'pixel' not in img_url and len(img_url) > 20:
                    featured_image = img_url

        projects.append({
            'title': title,
            'slug': slug,
            'lang': lang,
            'date': event_date,
            'content': content,
            'featured_image': featured_image,
            'gallery_images': gallery_images,
        })

    print(f"Found {len(projects)} published projects")
    for lang in ('ro', 'en', 'de'):
        count = sum(1 for p in projects if p['lang'] == lang)
        print(f"  {lang}: {count} projects")

    # Download gallery images and generate markdown
    print("\nProcessing projects...")
    for proj in projects:
        lang = proj['lang']
        slug = proj['slug']
        content = html_to_markdown(proj['content'])
        date = proj['date']
        title = proj['title'].replace('"', '\\"')

        # Download and localize featured image
        image_frontmatter = ''
        if proj['featured_image']:
            url = proj['featured_image']
            ext = os.path.splitext(url.split('?')[0])[1] or '.jpg'
            local_file = f"static/images/projects/{slug}{ext}"
            local_url = f"/images/projects/{slug}{ext}"
            local_path = os.path.join(BASE_DIR, local_file)
            if download_image(url, local_path):
                image_frontmatter = f'image: "{local_url}"'
            else:
                print(f"  WARN: Could not download featured image for {slug}")

        # Download gallery images
        local_gallery = []
        for i, gurl in enumerate(proj['gallery_images']):
            ext = os.path.splitext(gurl.split('?')[0])[1] or '.jpg'
            fname = f"{i+1:02d}{ext}"
            local_file = f"static/images/projects/galleries/{slug}/{fname}"
            local_url = f"/images/projects/galleries/{slug}/{fname}"
            local_path = os.path.join(BASE_DIR, local_file)
            if download_image(gurl, local_path):
                local_gallery.append(local_url)

        # Use first gallery image as featured if no featured image
        if not image_frontmatter and local_gallery:
            image_frontmatter = f'image: "{local_gallery[0]}"'

        # Build frontmatter
        fm_lines = [
            '---',
            f'title: "{title}"',
            f'date: {date}',
            'draft: false',
        ]
        if image_frontmatter:
            fm_lines.append(image_frontmatter)
        if local_gallery:
            fm_lines.append('gallery_images:')
            for gurl in local_gallery:
                fm_lines.append(f'  - "{gurl}"')
        fm_lines.append('---')

        frontmatter = '\n'.join(fm_lines)

        # Write file
        dir_path = os.path.join(BASE_DIR, 'content', lang_dir(lang), 'projects')
        os.makedirs(dir_path, exist_ok=True)
        filepath = os.path.join(dir_path, f'{slug}.md')

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(frontmatter + '\n\n' + content + '\n')

        gallery_note = f" + {len(local_gallery)} gallery imgs" if local_gallery else ""
        print(f"  Created: content/{lang_dir(lang)}/projects/{slug}.md{gallery_note}")

    print("\nDone!")


if __name__ == '__main__':
    main()
