#!/usr/bin/env python3
""" sequence repetitive profile conversion to GFF3 format """

import numpy as np
import time
from operator import itemgetter
from itertools import groupby
import configuration
 
 
def create_gff(seq_repeats, OUTPUT_GFF, THRESHOLD, THRESHOLD_SEGMENT):
	SOURCE = "Profrep"
	FEATURE = "Repeat"
	SCORE = "."
	STRAND = "."
	FRAME = "."
	header = seq_repeats.dtype.names
	seq_id = header[0]
	for repeat in header[2:]:
		above_th = seq_repeats[seq_id][np.where(seq_repeats[repeat] > THRESHOLD)[0]]
		ranges = idx_ranges(above_th, THRESHOLD_SEGMENT)
		#####
		if repeat == "G_Athila":
			print(ranges)
		#####
		with open(OUTPUT_GFF, "a") as gff:	
			for i in range(len(ranges) - 1)[::2]:
				gff.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\tName={}\n".format(seq_id, SOURCE, FEATURE, ranges[i], ranges[i + 1], SCORE, STRAND, FRAME, repeat))


def N_gff(header, sequence, N_GFF):
	SOURCE = "Profrep"
	FEATURE = "N_region"
	SCORE = "."
	STRAND = "."
	FRAME = "."
	name = "N"
	indices = [indices + 1 for indices, n in enumerate(sequence) if n == "n" or n == "N"]
	ranges = idx_ranges(indices, configuration.N_segment)
	with open(N_GFF, "a") as gff2:	
			for i in range(len(ranges) - 1)[::2]:
				gff2.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\tName={}\n".format(header, SOURCE, FEATURE, ranges[i], ranges[i + 1], SCORE, STRAND, FRAME, name))


def idx_ranges(indices, THRESHOLD_SEGMENT):
	ranges = []
	for key, group in groupby(enumerate(indices), lambda index_item: index_item[0] - index_item[1]):
			group = list(map(itemgetter(1), group))
			if len(group) > THRESHOLD_SEGMENT:
				# Take boundaries of the group vectors
				ranges.append(group[0])
				ranges.append(group[-1])
	return ranges

	
def main(args):
	OUTPUT = args.output
	OUTPUT_GFF = args.output_gff
	THRESHOLD = args.threshold
	THRESHOLD_SEGMENT = args.threshold_segment
	SEQ_INFO = args.seq_info
	with open(SEQ_INFO, "r") as s_info:
		next(s_info)
		for line in s_info:
			print(line)
			line_parsed = line.strip().split("\t")
			fasta_start = int(line_parsed[3])
			fasta_end = line_parsed[4]
			seq_length = int(line_parsed[1])
			seq_repeats = np.genfromtxt(OUTPUT, names=True, dtype="int", skip_header=fasta_start-1, max_rows=seq_length, delimiter="\t", deletechars="")
			gff.create_gff(seq_repeats, OUTPUT_GFF, THRESHOLD, THRESHOLD_SEGMENT)
 

if __name__ == "__main__":
	import argparse
	
	REPEATS_GFF = configuration.REPEATS_GFF
	SEQ_INFO = configuration.SEQ_INFO
	
	parser = argparse.ArgumentParser()
	parser.add_argument("-ou","--output",type=str, required=True,
						help="output profile table name")
	parser.add_argument('-ouf', '--output_gff', type=str, default=REPEATS_GFF,
                        help='output gff format')
	parser.add_argument("-th","--threshold",type=int, default=50,
						help="threshold for copy numbers (numbers of hits) at the  position to be considered as repetitive")
	parser.add_argument("-ths","--threshold_segment",type=int, default=50,
                        help="threshold for a single segment length to be reported as repetitive reagion in gff")
	parser.add_argument("-si", "--seq_info", type=str, default=SEQ_INFO,
                        help="file containg general info about sequence") 
	args = parser.parse_args()
	main(args)
