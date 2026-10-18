"""Translate complete whitespace-delimited panels, then return the selected browser image slice."""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

import requests
from split_webtoon import image_context, split_sources, restore_slice


def prepare_context(request, directory):
    urls, target = request['urls'], request['index']
    if not 1 <= len(urls) <= 300 or not isinstance(target, int) or not 0 <= target < len(urls):
        raise ValueError('Invalid episode image list')
    episode = urlsplit(urls[target]).path.split('/')[1:4]
    for url in urls:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname != 'image-comic.pstatic.net'
                or parsed.port not in (None, 443) or parsed.username or parsed.password
                or parsed.path.split('/')[1:4] != episode or episode[0] != 'webtoon'
                or not all(part.isdigit() for part in episode[1:])):
            raise ValueError('Only images from the same Naver episode are allowed')
    inputs = directory / 'inputs'
    inputs.mkdir(exist_ok=True)
    downloaded = 0

    def load(index):
        nonlocal downloaded
        print(f'Downloading context image {index}', flush=True)
        file = inputs / f'{index:04d}.img'
        with requests.get(urls[index], headers={'Referer': 'https://comic.naver.com/'},
                          allow_redirects=False, stream=True, timeout=(15, 30)) as response:
            if response.status_code != 200:
                raise ValueError(f'Image {index}: HTTP {response.status_code}')
            if response.headers.get('content-type', '').split(';')[0] not in {'image/jpeg', 'image/png', 'image/webp'}:
                raise ValueError('Unsupported image type')
            size = 0
            with file.open('wb') as output:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    downloaded += len(chunk)
                    if size > 20 * 1024 * 1024 or downloaded > 80 * 1024 * 1024:
                        raise ValueError('Image/context download exceeds the size limit')
                    output.write(chunk)
        return file

    sources, start, end, top, bottom = image_context(len(urls), target, load)
    page_map = split_sources(sources, directory / 'panels', start, end)
    context = {'index': target, 'top': top, 'bottom': bottom, 'input_files': [s['path'].name for s in sources],
               'page_map': page_map}
    (directory / 'context.json').write_text(json.dumps(context, indent=2), encoding='utf-8')
    return context


async def main(directory):
    request = json.loads((directory / 'request.json').read_text(encoding='utf-8'))
    context = prepare_context(request, directory)
    from translate_korean_sample import main as translate
    files = [directory / 'panels' / page['file'] for page in context['page_map']['pages']]
    records = await translate(output_dir=directory / 'translated', files=files)
    image = restore_slice(context['page_map'], directory / 'translated', context['top'], context['bottom'])
    image.save(directory / 'source.tmp.png')
    (directory / 'source.tmp.png').replace(directory / 'source.png')
    # Count only text overlapping the clicked strip, not text solely in neighbouring context.
    regions = sum(1 for page, record in zip(context['page_map']['pages'], records) for region in record['regions']
                  if max(point[1] for point in region['box']) + page['top'] > context['top']
                  and min(point[1] for point in region['box']) + page['top'] < context['bottom'])
    (directory / 'result.json').write_text(json.dumps({'regions': regions, 'panels': len(files),
                                                    'contextImages': len(context['input_files'])}), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    asyncio.run(main(parser.parse_args().directory.resolve()))
