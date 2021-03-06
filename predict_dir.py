#-*- coding:utf-8 -*-

from __future__ import division
from __future__ import absolute_import
from __future__ import print_function

import os
import torch
import argparse
import torch.nn as nn
import torch.utils.data as data
import torch.backends.cudnn as cudnn
import torchvision.transforms as transforms

import cv2
import time
import numpy as np
from PIL import Image

from data.config import cfg
from models.factory import build_net
from torch.autograd import Variable
from utils.augmentations import to_chw_bgr


parser = argparse.ArgumentParser(description='dsfd demo')
parser.add_argument('--network',
                    default='vgg', type=str,
                    choices=['vgg', 'resnet50', 'resnet101', 'resnet152'],
                    help='model for training')
parser.add_argument('--save_dir',
                    type=str, default='tmp/',
                    help='Directory for detect result')
parser.add_argument('--model',
                    type=str,
                    default='weight/pre_weight.pth', help='trained model')
parser.add_argument('--thresh',
                    default=0.2, type=float,
                    help='Final confidence threshold')
parser.add_argument('--video_dir',
                    default='./videos', type=str,
                    help='input videos path')
parser.add_argument('--freq',
                    default=3, type=int,
                    help='frequency')
parser.add_argument('--output_dir',
                    default='output', type=str,
                    help='for saving output videos')
args = parser.parse_args()


if not os.path.exists(args.save_dir):
    os.makedirs(args.save_dir)

use_cuda = torch.cuda.is_available()
if use_cuda:
    torch.set_default_tensor_type('torch.cuda.FloatTensor')
else:
    torch.set_default_tensor_type('torch.FloatTensor')
def find_no_match_box(pre_bbox,now_bbox,threshold=15):
    add_bbox = []
    if len(pre_bbox) > len(now_bbox):
        for A_box in pre_bbox:
            min_dis = 1000
            for B_box in now_bbox:
                cur_dis = np.sqrt(np.sum(np.square(A_box[0::1]-B_box[0::1])))
                if cur_dis<min_dis:
                    min_dis = cur_dis
            if min_dis > threshold:
                add_bbox.append(A_box)
    return add_bbox

def generate_mask(img_height,img_width,radius,center_x,center_y):
    y,x=np.ogrid[0:img_height,0:img_width]
    # circle mask
    # mask = (x-center_x)**2+(y-center_y)**2<=radius**2  
    # generate other masks （eg. heart-shaped）
    scale = 5/radius
    mask = 5*((-x+center_x)*scale)**2 - 6*np.abs((-x+center_x)*scale)*((-y+center_y)*scale) + 5*((-y+center_y)*scale)**2 < 128
    return mask
def detect(net, im, thresh,pre_bbox):
    #img = Image.open(img_path)
    
    img = Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB))  
    if img.mode == 'L':
        img = img.convert('RGB')

    img = np.array(img)
    height, width, _ = img.shape

    max_im_shrink = np.sqrt(
        1200 * 1000 / (img.shape[0] * img.shape[1]))
    image = cv2.resize(img, None, None, fx=max_im_shrink,
                       fy=max_im_shrink, interpolation=cv2.INTER_LINEAR)
    #image = cv2.resize(img,(224,),interpolation=cv2.INTER_LINEAR)
    x = to_chw_bgr(image)
    x = x.astype('float32')
    x -= cfg.img_mean
    x = x[[2, 1, 0], :, :]

    x = Variable(torch.from_numpy(x).unsqueeze(0))
    if use_cuda:
        x = x.cuda()
    #t1 = time.time()
    y = net(x)
    detections = y.data
    scale = torch.Tensor([img.shape[1], img.shape[0],
                          img.shape[1], img.shape[0]])

    #img = cv2.imread(img_path, cv2.IMREAD_COLOR)
    mask_img = np.ones(im.shape,np.int8)
    kernel_size = 15
    blur_img = cv2.blur(im,(kernel_size,kernel_size))
    
    now_bbox = []
    for i in range(detections.size(1)):
        j = 0
        while detections[0, i, j, 0] >= thresh:
            score = detections[0, i, j, 0]
            pt = (detections[0, i, j, 1:] * scale).cpu().numpy().astype(int)
            now_bbox.append(pt)
            j += 1
            x,y,w,h = pt[0], pt[1], pt[2]-pt[0], pt[3]-pt[1]
            mask=generate_mask(im.shape[0],im.shape[1],max(w,h)/2,x+w/2,y+h/2)
            mask_img[mask]=[0,0,0]

    add_bbox = find_no_match_box(pre_bbox,now_bbox)
    for bbox in add_bbox:
        score = bbox[0, i, j, 0]
        pt = bbox[0, i, j, 1:] * scale.numpy()
        j += 1
        x,y,w,h = pt[0], pt[1], pt[2]-pt[0], pt[3]-pt[1]
        mask=generate_mask(im.shape[0],im.shape[1],max(w,h)/2,x+w/2,y+h/2)
        mask_img[mask]=[0,0,0]
    now_bbox +=add_bbox
    mask_img_verse = np.ones(img.shape,np.int8) - mask_img
    result_img = mask_img * im + mask_img_verse * blur_img
    #t2 = time.time()
    #print('detect:{} timer:{}'.format(img_path, t2 - t1))

    #cv2.imwrite(os.path.join(args.save_dir, os.path.basename(img_path)), result_img)
    return result_img,now_bbox


if __name__ == '__main__':
    net = build_net('test', cfg.NUM_CLASSES, args.network)
    net.load_state_dict(torch.load(args.model))
    net.eval()

    if use_cuda:
        net.cuda()
        cudnn.benckmark = True
    #img_path = './test_pic'
    #img_list = [os.path.join(img_path, x)
    #            for x in os.listdir(img_path) if x.endswith('jpg')]
    #for path in img_list:
    #    detect(net, path, args.thresh)

    video_dir = args.video_dir
    for video_name in os.listdir(video_dir):
    	video_path = os.path.join(video_dir,video_name)
    	cap = cv2.VideoCapture(video_path)
    	fourcc = cv2.VideoWriter_fourcc("M", "J", "P", "G")
    	fps = cap.get(cv2.CAP_PROP_FPS)
    	size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), 
        	int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    	out = cv2.VideoWriter(os.path.join(args.output_dir,video_name.split('.')[0]+'.avi'),fourcc, fps, size)
    	timeF = args.freq
    	c = 0
    	T1 = time.time()
        pre_bbox = []
    	while (True):
            ret,im = cap.read()
            if ret == False:
                break
            if c%timeF == 0: 
                img,pre_bbox = detect(net,im,args.thresh,pre_bbox)
                frame = np.uint8(img)
                out.write(frame)
            c += 1
    	T2 = time.time()
    	print('detect {} time:{}'.format(video_name, T2 - T1))
    
    	cap.release()
    	out.release()
