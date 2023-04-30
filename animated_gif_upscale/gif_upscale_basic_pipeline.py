import argparse
import glob
import os
import logging
import sys
import shutil
import pathlib

import arrow
import humanize

import cv2

from basicsr.archs.rrdbnet_arch import RRDBNet
from basicsr.utils.download_util import load_file_from_url

from realesrgan import RealESRGANer
from realesrgan.archs.srvgg_arch import SRVGGNetCompact

# tell the wand module where imagemagick lives before trying to import it
os.environ['MAGICK_HOME'] = '/opt/homebrew/opt/imagemagick'
from wand.image import Image

if __name__ == '__main__':

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)

    working_base_dir = "../local/upscale_gif"

    # get the animated gif file name
    animated_gif_file_path = sys.argv[1]

    animated_gif_file_name = os.path.basename(animated_gif_file_path)
    animated_gif_id = pathlib.Path(animated_gif_file_name).stem

    animated_gif_img = Image(filename=animated_gif_file_path)

    working_dir = os.path.join(working_base_dir, animated_gif_id)
    if not os.path.exists(working_dir):
        os.makedirs(working_dir)

    # get the delay ticks between frames and geometry
    animated_gif_frame_delay_in_ticks = animated_gif_img.delay
    if animated_gif_frame_delay_in_ticks is None or animated_gif_frame_delay_in_ticks is 0:
        animated_gif_frame_delay_in_ticks = 8
    animated_gif_width = animated_gif_img.width
    animated_gif_height = animated_gif_img.height

    logging.info(f"{animated_gif_id} frames: {len(animated_gif_img.sequence)} h: {animated_gif_height} w: {animated_gif_width}")

    # set up real-ESRGAN to upscaler
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    netscale = 4
    file_url = ['https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.1/RealESRNet_x4plus.pth']

    model_name = "RealESRNet_x4plus"
    model_path = os.path.join(os.path.join(working_base_dir, 'weights'), model_name + '.pth')

    if not os.path.isfile(model_path):
        ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
        for url in file_url:
            # model_path will be updated
            model_path = load_file_from_url(url=url, model_dir=os.path.join(working_base_dir, 'weights'), progress=True, file_name=None)
    dni_weight = None

    tile = 0
    tile_pad = 10
    pre_pad = 0
    use_fp32 = True

    upsampler = RealESRGANer(
        scale=netscale,
        model_path=model_path,
        dni_weight=dni_weight,
        model=model,
        tile=tile,
        tile_pad=tile_pad,
        pre_pad=pre_pad,
        half=not use_fp32,
        gpu_id=None)


    # use imagemagick to split the gif into frames and upscale
    logging.info(f"{animated_gif_id} upscaling frames start")

    frame_count_places = len(list(str(len(animated_gif_img.sequence))))
    i = 0
    upsampling_scale = 4
    upscale_start_time = arrow.utcnow()
    upscaled_frame_file_names = []

    animated_gif_img.coalesce()

    for frame in animated_gif_img.sequence:
        frame_file_name = f"{animated_gif_id}_frame_{str(i).zfill(frame_count_places)}.png"
        frame_file_path = os.path.join(working_dir, frame_file_name)

        frame_upscaled_file_name = f"{animated_gif_id}_frame_{str(i).zfill(frame_count_places)}_upscaled.png"
        frame_upscaled_file_path = os.path.join(working_dir, frame_upscaled_file_name)

        upscaled_frame_file_names.append(frame_upscaled_file_path)

        Image(image=frame).save(filename=frame_file_path)

        img = cv2.imread(frame_file_path, cv2.IMREAD_UNCHANGED)
        output, _ = upsampler.enhance(img, outscale=upsampling_scale)
        cv2.imwrite(frame_upscaled_file_path, output)

        i += 1

    time_delta = arrow.utcnow() - upscale_start_time
    logging.info(f"{animated_gif_id} upscaling frames done. {humanize.time.precisedelta(time_delta)} ")

    # re-combine the upscaled frames into a new animated gif with original delay ticks
    with Image() as upscaled_gif_img:
        for frame_upscaled_file_name in  upscaled_frame_file_names:
            with Image(filename=frame_upscaled_file_name) as upscaled_frame_img:
                upscaled_gif_img.sequence.append(upscaled_frame_img)

        for cursor in range(len(upscaled_gif_img.sequence)):
            with upscaled_gif_img.sequence[cursor] as frame:
                frame.delay = animated_gif_frame_delay_in_ticks
        # Set layer type
        upscaled_gif_img.type = 'optimize'
        upscaled_gif_img.save(filename=os.path.join(working_dir, f"{animated_gif_id}_upscaled.gif"))
        upscaled_gif_img.close()

    # create a version of the upscaled gif with the geometry of the original gif
    shutil.copy(os.path.join(working_dir, f"{animated_gif_id}_upscaled.gif"),
                os.path.join(working_dir, f"{animated_gif_id}_upscaled_resized..gif"))

    upscaled_resized_gif_img=Image(filename=os.path.join(working_dir, f"{animated_gif_id}_upscaled_resized..gif"))
    upscaled_resized_gif_img.resize(animated_gif_width, animated_gif_height)
    upscaled_resized_gif_img.save(filename=os.path.join(working_dir, f"{animated_gif_id}_upscaled_resized..gif"))
    upscaled_resized_gif_img.close()


    logging.info(f"{animated_gif_id} done creating upscaled gif.")

