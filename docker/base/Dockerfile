# syntax = docker/dockerfile:experimental

FROM ubuntu:18.04

ENV IN_RACER_DOCKER 1
ENV DEBIAN_FRONTEND noninteractive

RUN echo "[racer] <base> start" && \
	\
	apt-get update && apt-get install -y apt-utils && apt-get upgrade -y && \
	\
	apt-get install -y \
		build-essential \
		autoconf cmake pkg-config \
		texinfo flex bison bc gettext \
		python3.7 python3.7-dev python3-distutils python3-pip \
		git curl wget doxygen cpio rsync kmod \
		libcap2 libcap-dev libattr1 libattr1-dev \
		libglib2.0-dev libfdt-dev libpixman-1-dev \
		libncurses-dev libelf-dev libssl-dev \
		libblkid-dev libzstd-dev liblzo2-dev \
		libgl1-mesa-glx \
		libtool && \
	\
	update-alternatives --install \
		/usr/bin/python3 python3 /usr/bin/python3.7 1 && \
	\
	pip3 install \
		asciitree termcolor \
		sortedcontainers \
		lark-parser graphviz PySide2 && \
	\
	cd /root && \
		wget https://cmake.org/files/v3.14/cmake-3.14.4.tar.gz && \
		tar xvf cmake-3.14.4.tar.gz && \
		cd cmake-3.14.4 && \
		./bootstrap -- -DCMAKE_BUILD_TYPE:STRING=Release && \
		make -j$(nproc) && make install && \
		cd /root && \
		rm -rf cmake-* && \
	\
	echo "[racer] <base> ready"

ENV DEBIAN_FRONTEND teletype
