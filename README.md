# krace : End-to-end fuzzing framework

krace bring coverage-guided fuzzing to the concurrency dimension with three new constructs: 1) a new coverage tracking metric, alias coverage, specially designed to capture the exploration progress in the concurrency dimension; 2) an evolution algorithm for generating, mutating, and merging multi-threaded syscall sequences as inputs for concurrency fuzzing; and 3) a comprehensive lockset and happens-before modeling for kernel synchronization primitives for precise data race detection. These components are integrated into Krace, an end-to-end fuzzing framework that has discovered 23 data races in ext4, btrfs, and the VFS layer so far, and 9 are confirmed to be harmful.

This repository is provided under the terms of MIT license.

## Reference
https://ieeexplore.ieee.org/abstract/document/9152693
```
@INPROCEEDINGS{9152693,
  author={Xu, Meng and Kashyap, Sanidhya and Zhao, Hanqing and Kim, Taesoo},
  booktitle={2020 IEEE Symposium on Security and Privacy (SP)}, 
  title={Krace: Data Race Fuzzing for Kernel File Systems}, 
  year={2020},
  volume={},
  number={},
  pages={1643-1660},
  doi={10.1109/SP40000.2020.00078}}
```
