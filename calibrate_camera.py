import cv2
import numpy as np
import glob
import os

CHECKERBOARD = (9, 7)  # Adjust based on your checkerboard

objp = np.zeros((np.prod(CHECKERBOARD), 3), np.float32)
objp[:, :2] = np.indices(CHECKERBOARD).T.reshape(-1, 2)
objp *= 25  # Square size in mm; adjust as per your checkerboard

objpoints = []  # 3D points in real world space
imgpoints = []  # 2D points in image plane

images = glob.glob('path_to_images/*.jpg')  # Adjust the path and extension as needed

for fname in images:
    img = cv2.imread(fname)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD, None)
    if ret:
        objpoints.append(objp)
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), 
                                    criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
        imgpoints.append(corners2)

        cv2.drawChessboardCorners(img, CHECKERBOARD, corners2, ret)
        cv2.imshow('img', img)
        cv2.waitKey(500)

cv2.destroyAllWindows()

ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)

np.savez('calibration_data.npz', mtx=mtx, dist=dist, rvecs=rvecs, tvecs=tvecs)

