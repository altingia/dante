#!/usr/bin/env python3

import numpy as np
import subprocess
import csv
import time
import sys
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.cm as cmx
import multiprocessing
import argparse
import os
from functools import partial
from multiprocessing import Pool
from tempfile import NamedTemporaryFile
from operator import itemgetter
from itertools import groupby
import gff
import protein_domains_pd
import domains_filtering
import configuration
import visualization
import distutils
from distutils import dir_util
import tempfile
import re
from Bio import SeqIO
import sys
import pickle

t_profrep = time.time()
np.set_printoptions(threshold=np.nan)

def check_fasta_id(QUERY):
	forbidden_ids = []
	for record in SeqIO.parse(QUERY, "fasta"):
		if any(x in record.id for x in configuration.FORBIDDEN_CHARS):
		 forbidden_ids.append(record.id)	
	return forbidden_ids


def multifasta(QUERY):
	''' Create single fasta temporary files to be processed sequentially '''
	PATTERN = ">"
	fasta_list = []
	with open(QUERY, "r") as fasta:
		reader = fasta.read()
		splitter = reader.split(PATTERN)[1:]
		for fasta_num, part in enumerate(splitter):
			ntf = NamedTemporaryFile(delete=False)
			ntf.write("{}{}".format(PATTERN, part).encode("utf-8"))
			fasta_list.append(ntf.name)
			ntf.close()
		return fasta_list


def fasta_read(subfasta):
	''' Read fasta, gain header and sequence without gaps '''
	sequence_lines = []
	with open(subfasta, "r") as fasta:
		header = fasta.readline().strip().split(" ")[0][1:]
		for line in fasta:
			clean_line = line.strip()			
			if clean_line:				
				sequence_lines.append(clean_line)
	sequence = "".join(sequence_lines)
	return header, sequence


def cluster_annotation(CL_ANNOTATION_TBL):
	''' Create dictionary of known annotations classes and related clusters '''
	cl_annotations = {} 			
	annot_table = np.genfromtxt(CL_ANNOTATION_TBL, dtype=str) 
	for line in annot_table:
		if line[1] in cl_annotations:
			cl_annotations[line[1]].append(line[0])
		else:
			cl_annotations[line[1]] = [line[0]]
	return list(cl_annotations.items()), list(cl_annotations.keys())


def read_annotation(CLS, cl_annotations_items):
	''' Dictionary of known repeat classes and related reads '''
	reads_annotations = {} 	
	with open(CLS, "r") as cls_file:
		count = 0
		for line in cls_file:
			line = line.rstrip()
			count += 1
			if count%2 == 0:
				reads = re.split("\s+", line) 
				for element in reads: 
					for key, value in cl_annotations_items:
						if clust in value:
							reads_annotations[element] = key 
			else:
				clust = re.split("\s+", line)[0].split(">CL")[1]
	return reads_annotations


def annot_profile(annotation_keys, part):
	''' Predefine dictionary of known annotations and partial sequence 
	repetitive profiles defined by parallel process '''
	subprofile = {} 				
	for key in annotation_keys:
		subprofile[key] = np.zeros(part, dtype=int)
	subprofile["ALL"] = np.zeros(part, dtype=int)
	return subprofile


def parallel_process(WINDOW, OVERLAP, seq_length, annotation_keys, reads_annotations, subfasta, BLAST_DB, E_VALUE, WORD_SIZE, BLAST_TASK, MAX_ALIGNMENTS, MIN_IDENTICAL, MIN_ALIGN_LENGTH, DUST_FILTER, last_index, subsets_num, subset_index):
	''' Run parallel function to process the input sequence in windows
		Run blast for subsequence defined by the input index and window size
 		Create and increment subprofile vector based on reads aligned within window '''
	loc_start = subset_index + 1
	loc_end = subset_index + WINDOW
	if loc_end > seq_length:
		loc_end = seq_length
		subprofile = annot_profile(annotation_keys, seq_length - loc_start + 1)
	else:
		subprofile = annot_profile(annotation_keys, WINDOW + 1)
	
	# Find HSP records for every window defined by query location and parse the tabular stdout:
	# 1. query, 2. database read, 3. %identical, 4. alignment length, 5. alignment start, 6. alignment end
	p = subprocess.Popen("blastn -query {} -query_loc {}-{} -db {} -evalue {} -word_size {} -dust {} -task {} -num_alignments {} -outfmt '6 qseqid sseqid pident length qstart qend'".format(subfasta, loc_start, loc_end, BLAST_DB, E_VALUE, WORD_SIZE, DUST_FILTER, BLAST_TASK, MAX_ALIGNMENTS), stdout=subprocess.PIPE, shell=True)
	for line in p.stdout:
		column = line.decode("utf-8").rstrip().split("\t")
		if float(column[2]) >= MIN_IDENTICAL and int(column[3]) >= MIN_ALIGN_LENGTH:
			read = column[1]				# ID of individual aligned read
			if "reduce" in read:
				reads_representation = int(read.split("reduce")[-1])
			else:
				reads_representation = 1
			qstart = int(column[4])			# starting position of alignment
			qend = int(column[5])			# ending position of alignemnt
			if read in reads_annotations:
				annotation = reads_annotations[read]								
			else:
				annotation = "ALL"
			subprofile[annotation][qstart-subset_index-1 : qend-subset_index] = subprofile[annotation][qstart-subset_index-1 : qend-subset_index] + reads_representation
	subprofile["ALL"] = sum(subprofile.values())
	if subset_index == 0: 
		if subsets_num == 1:
			subprf_name = subprofile_single(subprofile, subset_index)
		else:
			subprf_name = subprofile_first(subprofile, subset_index, WINDOW, OVERLAP)
	elif subset_index == last_index:
		subprf_name = subprofile_last(subprofile, subset_index, OVERLAP)
	else:
		subprf_name = subprofiles_middle(subprofile, subset_index, WINDOW, OVERLAP)
	return subprf_name
	
	
def subprofile_single(subprofile, subset_index):
	subprofile['idx'] = list(range(1, len(subprofile["ALL"]) + 1))
	subprf_dict = NamedTemporaryFile(suffix='{}_.pickle'.format(subset_index),delete=False)
	with open(subprf_dict.name, 'wb') as handle:
		pickle.dump(subprofile, handle, protocol=pickle.HIGHEST_PROTOCOL)
	subprf_dict.close()
	return subprf_dict.name


def subprofile_first(subprofile, subset_index, WINDOW, OVERLAP):
	for key in subprofile.keys():
		subprofile[key] = subprofile[key][0 : -OVERLAP//2-1]
	subprofile['idx'] = list(range(subset_index + 1, subset_index + WINDOW-OVERLAP//2 + 1))
	subprf_dict = NamedTemporaryFile(suffix='{}_.pickle'.format(subset_index),delete=False)
	with open(subprf_dict.name, 'wb') as handle:
		pickle.dump(subprofile, handle, protocol=pickle.HIGHEST_PROTOCOL)
	subprf_dict.close()
	return subprf_dict.name
	
	
def subprofiles_middle(subprofile, subset_index, WINDOW, OVERLAP):
	for key in subprofile.keys():
		subprofile[key] = subprofile[key][OVERLAP//2 : -OVERLAP//2-1]
	subprofile['idx'] = list(range(subset_index + OVERLAP//2 + 1, subset_index + WINDOW-OVERLAP//2 + 1))
	subprf_dict = NamedTemporaryFile(suffix='{}_.pickle'.format(subset_index),delete=False)
	with open(subprf_dict.name, 'wb') as handle:
		pickle.dump(subprofile, handle, protocol=pickle.HIGHEST_PROTOCOL)
	subprf_dict.close()
	return subprf_dict.name


def subprofile_last(subprofile, subset_index, OVERLAP):
	len_subprofile = len(subprofile['ALL'])
	for key in subprofile.keys():
		subprofile[key] = subprofile[key][OVERLAP//2:]
	subprofile['idx'] = list(range(subset_index + OVERLAP//2 + 1, subset_index + len_subprofile +1))
	subprf_dict = NamedTemporaryFile(suffix='{}_.pickle'.format(subset_index),delete=False)
	with open(subprf_dict.name, 'wb') as handle:
		pickle.dump(subprofile, handle, protocol=pickle.HIGHEST_PROTOCOL)
	subprf_dict.close()
	return subprf_dict.name
	
											
def concatenate_prof(subprofiles_all, files_dict, seq_id, HTML_DATA):
	for subprofile in subprofiles_all:
		with open(subprofile, 'rb') as handle:
			individual_dict = pickle.load(handle)
			exclude = set(["idx"])
			for key in set(individual_dict.keys()).difference(exclude):
				if any(individual_dict[key]):
					indices = handle_zero_lines(individual_dict[key])
					if key not in files_dict.keys():
						prf_name = "{}/{}.wig".format(HTML_DATA, re.sub('[\/\|]','_',key))
						with open(prf_name, "a") as prf_file:
							prf_file.write("{}{}\n".format(configuration.HEADER_WIG, seq_id))
							for i in indices:
								prf_file.write("{}\t{}\n".format(individual_dict['idx'][i], individual_dict[key][i]))
						files_dict[key] = [prf_name,[seq_id]]
					else:
						prf_name = files_dict[key][0]
						with open(prf_name, "a") as prf_file:
							if seq_id not in files_dict[key][1]:
								prf_file.write("{}{}\n".format(configuration.HEADER_WIG, seq_id))
								files_dict[key][1].append(seq_id)
							for i in indices:
								prf_file.write("{}\t{}\n".format(individual_dict['idx'][i], individual_dict[key][i]))
	return files_dict


def concatenate_prof_CV(CV, subprofiles_all, files_dict, seq_id, HTML_DATA):
	for subprofile in subprofiles_all:
		with open(subprofile, 'rb') as handle:
			individual_dict = pickle.load(handle)
			exclude = set(["idx"])
			for key in set(individual_dict.keys()).difference(exclude):
				if any(individual_dict[key]):
					indices = handle_zero_lines(individual_dict[key])
					if key not in files_dict.keys():
						prf_name = "{}/{}.wig".format(HTML_DATA, re.sub('[\/\|]','_',key))
						with open(prf_name, "a") as prf_file:
							prf_file.write("{}{}\n".format(configuration.HEADER_WIG, seq_id))
							for i in indices:
								prf_file.write("{}\t{}\n".format(individual_dict['idx'][i], int(individual_dict[key][i]/CV)))
						files_dict[key] = [prf_name,[seq_id]]
					else:
						prf_name = files_dict[key][0]
						with open(prf_name, "a") as prf_file:
							if seq_id not in files_dict[key][1]:
								prf_file.write("{}{}\n".format(configuration.HEADER_WIG, seq_id))
								files_dict[key][1].append(seq_id)
							for i in indices:
								prf_file.write("{}\t{}\n".format(individual_dict['idx'][i], int(individual_dict[key][i]/CV)))
	return files_dict
		

def handle_zero_lines(repeat_subhits):
	''' Clean lines which contains only zeros, i.e. positons which do not contain any hit. However border zero positions need to be preserved due to correct graphs plotting '''
	zero_idx = [idx for idx, val in enumerate(repeat_subhits) if val == 0]
	indices = [idx for idx, val in enumerate(repeat_subhits) if val != 0]
	zero_breakpoints = []
	for key, group in groupby(enumerate(zero_idx), lambda index_item: index_item[0] - index_item[1]):
		group = list(map(itemgetter(1),group))
		zero_breakpoints.append(group[0])
		zero_breakpoints.append(group[-1])
	if indices:
		indices.extend(zero_breakpoints)
		indices = sorted(set(indices), key=int)	
	else:
		indices = []
	return indices
	

def repeats_process_dom(OUTPUT_GFF, THRESHOLD, THRESHOLD_SEGMENT, HTML_DATA, xminimal, xmaximal, domains, seq_ids_dom, CV, seq_ids_all, seq_lengths_all, files_dict):
	''' Process the hits table separately for each fasta, create gff file and profile picture '''
	################################################### ZBYTOCNE !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
	#gff_repeats = open(OUTPUT_GFF, "a")
	####################################################################
	if files_dict:
		gff.create_gff(THRESHOLD, THRESHOLD_SEGMENT, OUTPUT_GFF, files_dict, seq_ids_all)
		#gff.create_gff(THRESHOLD, THRESHOLD_SEGMENT, gff_repeats, files_dict, seq_ids_all)
	else:
		with open(OUTPUT_GFF, "w") as gff_file:
			gff_file.write("{}\n".format(configuration.HEADER_GFF))
	if len(seq_ids_all) <= configuration.MAX_PIC_NUM:
		################################################################
		#####vykreslovat prvych 50########### !!!!!!!!!!!!!!!!!!!!!!!!!!
		################################################################
		graphs_dict = {}
		if files_dict:	
			graphs_dict = visualization.vis_profrep(seq_ids_all, files_dict, seq_lengths_all, CV, HTML_DATA)
		count_seq = 0
		print(seq_ids_all)
		print(seq_ids_dom)
		for seq in seq_ids_all:
			if seq not in graphs_dict.keys():
				[fig, ax] = visualization.plot_figure(seq, seq_lengths_all[count_seq], CV)
				ax.hlines(0, 0, seq_lengths_all[count_seq], color="red", lw=4)
			else:
				fig = graphs_dict[seq][0]
				ax = graphs_dict[seq][1]
				art = []
				lgd = ax.legend(bbox_to_anchor=(0.5,-0.1), loc=9, ncol=3)
				art.append(lgd)
			if seq in seq_ids_dom:
				dom_idx = seq_ids_dom.index(seq) 
				[fig, ax] = visualization.vis_domains(fig, ax, seq, xminimal[dom_idx], xmaximal[dom_idx], domains[dom_idx])
			output_pic_png = "{}/{}.png".format(HTML_DATA, count_seq)
			fig.savefig(output_pic_png, bbox_inches="tight", format="png", dpi=configuration.IMAGE_RES)
			count_seq += 1
	#gff_repeats.close()	
	return None
	
	
def repeats_process(OUTPUT_GFF, THRESHOLD, THRESHOLD_SEGMENT, HTML_DATA, CV, seq_ids_all, seq_lengths_all, files_dict):
	''' Process the hits table separately for each fasta, create gff file and profile picture '''
	#gff_repeats = open(OUTPUT_GFF, "a")
	####################################################################
	################co s tym???
	####################################################################	
	if files_dict:
		gff.create_gff(THRESHOLD, THRESHOLD_SEGMENT, OUTPUT_GFF, files_dict, seq_ids_all)
		#gff.create_gff(THRESHOLD, THRESHOLD_SEGMENT, gff_repeats, files_dict, seq_ids_all)
	else:
		with open(OUTPUT_GFF, "w") as gff_file:
			gff_file.write("{}\n".format(configuration.HEADER_GFF))
	if len(seq_ids_all) <= configuration.MAX_PIC_NUM:
		################################################################
		##################vykreslovat prvych 50!!!!!!!!!################
		################################################################
		graphs_dict = {}
		if files_dict:	
			graphs_dict = visualization.vis_profrep(seq_ids_all, files_dict, seq_lengths_all, CV, HTML_DATA)
		count_seq = 0
		for seq in seq_ids_all:
			if seq not in graphs_dict.keys():
				[fig, ax] = visualization.plot_figure(seq, seq_lengths_all[count_seq], CV)
				ax.hlines(0, 0, seq_lengths_all[count_seq], color="red", lw=4)
			else:
				fig = graphs_dict[seq][0]
				ax = graphs_dict[seq][1]
				art = []
				lgd = ax.legend(bbox_to_anchor=(0.5,-0.1), loc=9, ncol=3)
				art.append(lgd)
			output_pic_png = "{}/{}.png".format(HTML_DATA, count_seq)
			fig.savefig(output_pic_png, bbox_inches="tight", format="png", dpi=configuration.IMAGE_RES)	
			plt.close()
			count_seq += 1
	#gff_repeats.close()	
	return None
	

def html_output(total_length, seq_lengths_all, seq_names, HTML, DB_NAME, REF, REF_LINK):
	''' Define html output with limited number of output pictures and link to JBrowse '''
	info = "\t\t".join(['<pre> {} [{} bp]</pre>'.format(seq_name, seq_length) for seq_name, seq_length in zip(seq_names, seq_lengths_all)])
	if REF:
		ref_part_1 = REF.split("-")[0]
		ref_part_2 = "-".join(REF.split("-")[1:]).split(". ")[0]
		ref_part_3 = ". ".join("-".join(REF.split("-")[1:]).split(". ")[1:])
		ref_string = '''<h6> {} - <a href="{}" target="_blank" >{}</a>. {}'''.format(ref_part_1, REF_LINK, ref_part_2, ref_part_3)
		database = DB_NAME
	else:
		ref_string = "Custom Data"
		database = "CUSTOM"
	pictures = "\n\t\t".join(['<img src="{}.png" width=1800>'.format(pic)for pic in range(len(seq_names))[:configuration.MAX_PIC_NUM]])
	html_str = '''
	<!DOCTYPE html>
	<html>
	<body>
		<h2>PROFREP OUTPUT</h2>
		<h4> Sequences processed: </h4>
		{}
		<h4> Total length: </h4>
		<pre> {} bp </pre>
		<h4> Database: </h4>
		<pre> {} </pre>
		<hr>
		<h3> Repetitive profile(s)</h3> </br>
		{} <br/>
		<h4>References: </h4>
		{}
		</h6>
	</body>
	</html>
	'''.format(info, total_length, database, pictures, ref_string)
	with open(HTML,"w") as html_file:
		html_file.write(html_str)


def jbrowse_prep_dom(HTML_DATA, QUERY, OUT_DOMAIN_GFF, OUTPUT_GFF, N_GFF, total_length, JBROWSE_BIN, files_dict):
	''' Set up the paths, link and convert output data to be displayed as tracks in Jbrowse '''
	jbrowse_data_path = os.path.join(HTML_DATA, configuration.jbrowse_data_dir)
	with tempfile.TemporaryDirectory() as dirpath:
		subprocess.call(["{}/prepare-refseqs.pl".format(JBROWSE_BIN), "--fasta", QUERY, "--out", jbrowse_data_path])
		subprocess.call(["{}/flatfile-to-json.pl".format(JBROWSE_BIN), "--gff", OUT_DOMAIN_GFF, "--trackLabel", "GFF_domains", "--out",  jbrowse_data_path])
		subprocess.call(["{}/flatfile-to-json.pl".format(JBROWSE_BIN), "--gff", OUTPUT_GFF, "--trackLabel", "GFF_repeats", "--config", configuration.JSON_CONF_R, "--out",  jbrowse_data_path])
		subprocess.call(["{}/flatfile-to-json.pl".format(JBROWSE_BIN), "--gff", N_GFF, "--trackLabel", "N_regions", "--config", configuration.JSON_CONF_N, "--out",  jbrowse_data_path])		 
		count = 0
		# Control the total length processed, if above threshold, dont create wig image tracks 
		if total_length <= configuration.WIG_TH and files_dict:
			exclude = set(['ALL'])
			sorted_keys =  sorted(set(files_dict.keys()).difference(exclude))
			sorted_keys.insert(0, "ALL")
			for repeat_id in sorted_keys:
				color = configuration.COLORS_RGB[count]
				subprocess.call(["{}/wig-to-json.pl".format(JBROWSE_BIN), "--wig", "{}".format(files_dict[repeat_id][0]), "--trackLabel", repeat_id, "--fgcolor", color, "--out",  jbrowse_data_path])
				count += 1
		distutils.dir_util.copy_tree(dirpath,jbrowse_data_path)
	return None
	
	
def jbrowse_prep(HTML_DATA, QUERY, OUTPUT_GFF, N_GFF, total_length, JBROWSE_BIN, files_dict):
	''' Set up the paths, link and convert output data to be displayed as tracks in Jbrowse '''
	jbrowse_data_path = os.path.join(HTML_DATA, configuration.jbrowse_data_dir)
	with tempfile.TemporaryDirectory() as dirpath:
		subprocess.call(["{}/prepare-refseqs.pl".format(JBROWSE_BIN), "--fasta", QUERY, "--out", jbrowse_data_path])
		subprocess.call(["{}/flatfile-to-json.pl".format(JBROWSE_BIN), "--gff", OUTPUT_GFF, "--trackLabel", "GFF_repeats", "--config", configuration.JSON_CONF_R, "--out",  jbrowse_data_path])
		subprocess.call(["{}/flatfile-to-json.pl".format(JBROWSE_BIN), "--gff", N_GFF, "--trackLabel", "N_regions", "--config", configuration.JSON_CONF_N, "--out",  jbrowse_data_path])		 
		count = 0
		# Control the total length processed, if above threshold, dont create wig image tracks 
		if total_length <= configuration.WIG_TH and files_dict:
			exclude = set(['ALL'])
			sorted_keys =  sorted(set(files_dict.keys()).difference(exclude))
			sorted_keys.insert(0, "ALL")
			for repeat_id in sorted_keys:
				color = configuration.COLORS_RGB[count]
				subprocess.call(["{}/wig-to-json.pl".format(JBROWSE_BIN), "--wig", "{}".format(files_dict[repeat_id][0]), "--trackLabel", repeat_id, "--fgcolor", color, "--out",  jbrowse_data_path])
				count += 1
		distutils.dir_util.copy_tree(dirpath,jbrowse_data_path)
	return None
	

def genome2coverage(GS, BLAST_DB):
	''' Convert genome size to coverage '''
	nr = subprocess.Popen('''cat {} | grep '>' | wc -l'''.format(BLAST_DB), stdout=subprocess.PIPE, shell=True)
	num_of_reads = int(nr.communicate()[0])
	########################################### !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!#########################################################
	lr = subprocess.Popen('''awk -v N=2 '{print}/>/&&--N<=0{exit}' ''' + BLAST_DB + '''| awk '$0 !~">"{print}' | awk '{sum+=length($0)}END{print sum}' ''', stdout=subprocess.PIPE, shell=True)
	len_of_read = int(lr.communicate()[0])
	CV = (num_of_reads*len_of_read)/(GS*1000000) # GS in Mbp
	print("COVERAGE = {}".format(CV))
	return CV

	
def prepared_data(TBL, DB_ID, TOOL_DATA_DIR):
	''' Get prepared rep. annotation data from the table based on the selected species ID '''
	with open(TBL) as datasets:
		for line in datasets:
			if line.split("\t")[0] == DB_ID:
				DB_NAME = line.split("\t")[1]
				BLAST_DB = os.path.join(TOOL_DATA_DIR, line.split("\t")[2])
				print(BLAST_DB)
				CLS = os.path.join(TOOL_DATA_DIR, line.split("\t")[3])
				CL_ANNOTATION_TBL = os.path.join(TOOL_DATA_DIR, line.split("\t")[4])
				CV = float(line.split("\t")[5])
				REF = line.split("\t")[6]
				REF_LINK = line.split("\t")[7]
	return DB_NAME, BLAST_DB, CLS, CL_ANNOTATION_TBL, CV, REF, REF_LINK

	
def main(args):
	
	## Command line arguments
	QUERY = args.query
	BLAST_DB = args.database
	CL_ANNOTATION_TBL = args.annotation_tbl 
	CLS = args.cls
	MIN_IDENTICAL = args.identical
	MIN_ALIGN_LENGTH = args.align_length
	E_VALUE = args.e_value
	WORD_SIZE = args.word_size
	WINDOW = args.window
	OVERLAP = args.overlap
	BLAST_TASK = args.task
	MAX_ALIGNMENTS = args.max_alignments
	NEW_DB = args.new_db
	THRESHOLD = args.threshold
	THRESHOLD_SEGMENT = args.threshold_segment
	#OUTPUT = args.output
	OUTPUT_GFF = args.output_gff
	DOMAINS = args.protein_domains
	LAST_DB = args.protein_database
	CLASSIFICATION = args.classification
	OUT_DOMAIN_GFF = args.domain_gff	
	HTML = args.html_file
	HTML_DATA = args.html_path
	N_GFF = args.n_gff
	CV = args.coverage
	CN = args.copy_numbers
	GS = args.genome_size
	DB_ID = args.db_id
	TBL = args.datasets_tbl
	DB_NAME = args.db_name
	THRESHOLD_SCORE = args.threshold_score
	WIN_DOM = args.win_dom
	OVERLAP_DOM = args.overlap_dom
	THRESHOLD_SCORE = args.threshold_score
	WIN_DOM = args.win_dom
	OVERLAP_DOM = args.overlap_dom
	GALAXY = args.galaxy_usage
	TOOL_DATA_DIR = args.tool_dir
	JBROWSE_BIN = args.jbrowse_bin
	DUST_FILTER = args.dust_filter
	LOG_FILE = args.log_file
	#REDUCED_DB = args.reduced_db

	REF = None
	REF_LINK = None
	
	print(DB_ID)
	#if "reduced" in DB_ID:
		#REDUCED_DB = True 
		#print("reduced")

	## Check if there are forbidden characters in fasta IDs 
	forbidden_ids = check_fasta_id(QUERY)
	if forbidden_ids:
		raise UserWarning("The following IDs contain forbidden characters ('/' or '\\') - PLEASE REPLACE OR DELETE THEM:\n{}".format("\n".join(forbidden_ids)))

	
	## Parse prepared annotation data table
	if TBL:
		#TBL = os.path.join(configuration.PROFREP_DATA, TBL)
		[DB_NAME, BLAST_DB, CLS, CL_ANNOTATION_TBL, CV, REF, REF_LINK] = prepared_data(TBL, DB_ID, TOOL_DATA_DIR)
	if GALAXY:
		LAST_DB = os.path.join(LAST_DB, configuration.LAST_DB_FILE)
		CLASSIFICATION = os.path.join(CLASSIFICATION, configuration.CLASS_FILE)

	
	## Calculate coverage 
	if not CN:
		CV = False
		
	## Create new blast database of reads
	if NEW_DB:
		subprocess.call("makeblastdb -in {} -dbtype nucl".format(BLAST_DB), shell=True)
	
	## Create dir to store outputs for html 
	if not os.path.exists(HTML_DATA):
		os.makedirs(HTML_DATA)
		
	if not os.path.isabs(OUT_DOMAIN_GFF):
		OUT_DOMAIN_GFF = os.path.join(HTML_DATA, OUT_DOMAIN_GFF)
	
	if not os.path.isabs(HTML):
		HTML = os.path.join(HTML_DATA, HTML)
	
	if not os.path.isabs(LOG_FILE):
		LOG_FILE = os.path.join(HTML_DATA, LOG_FILE)

	## Define parameters for parallel process
	STEP = WINDOW - OVERLAP		
	NUM_CORES = multiprocessing.cpu_count()	
	with open(LOG_FILE, "w") as log:
		log.write("NUM_OF_CORES = {}\n".format(NUM_CORES))
	log = open(LOG_FILE,"a")
	parallel_pool = Pool(NUM_CORES)

	## Assign clusters to repetitive classes
	[cl_annotations_items, annotation_keys] = cluster_annotation(CL_ANNOTATION_TBL)
	
	## Assign reads to repetitive classes
	reads_annotations = read_annotation(CLS, cl_annotations_items)
	
	## Convert genome size to coverage
	if GS:
		CV = genome2coverage(GS, BLAST_DB)
	
	## Detect all fasta sequences from input
	fasta_list = multifasta(QUERY)
	headers=[]
	files_dict = {}
	seq_count = 1
	start = 1
	total_length = 0
	seq_lengths_all = [] 
	with open(N_GFF, "w") as Ngff:
		Ngff.write("{}\n".format(configuration.HEADER_GFF))
	Ngff = open(N_GFF,"a")
		
	## Find hits for each fasta sequence separetely
	t_blast=time.time()	
	for subfasta in fasta_list:
		[header, sequence] = fasta_read(subfasta)
		################################################################
		indices_N = [indices + 1 for indices, n in enumerate(sequence) if n == "n" or n == "N"]
		if indices_N:
			gff.idx_ranges_N(indices_N, configuration.N_segment, header, Ngff, configuration.N_NAME, configuration.N_FEATURE)
		################################################################
		#gff.N_gff(header, sequence, Ngff)
		seq_length = len(sequence)
		headers.append(header)
		#with open(OUTPUT, 'a') as profile_tbl:
			#profile_tbl.write( "{}\tALL\t{}\n".format(header, "\t".join(sorted(set(annotation_keys).difference(set(["ALL"]))))))
		## Create parallel process																							
		subset_index = list(range(0, seq_length, STEP))
		## Situation when penultimal window is not complete but it is following by another one
		if len(subset_index) > 1 and subset_index[-2] + WINDOW >= seq_length:
			subset_index = subset_index[:-1]	
		last_index = subset_index[-1]
		index_range = range(len(subset_index))
		for chunk_index in index_range[0::configuration.MAX_FILES_SUBPROFILES]:
			#if REDUCED_DB:
				#print("reduced_db")
				#multiple_param = partial(parallel_process_reduced, WINDOW, OVERLAP, seq_length, annotation_keys, reads_annotations, subfasta, BLAST_DB, E_VALUE, WORD_SIZE, BLAST_TASK, MAX_ALIGNMENTS, MIN_IDENTICAL, MIN_ALIGN_LENGTH, DUST_FILTER, last_index, len(subset_index))
			#else:
			multiple_param = partial(parallel_process, WINDOW, OVERLAP, seq_length, annotation_keys, reads_annotations, subfasta, BLAST_DB, E_VALUE, WORD_SIZE, BLAST_TASK, MAX_ALIGNMENTS, MIN_IDENTICAL, MIN_ALIGN_LENGTH, DUST_FILTER, last_index, len(subset_index))
			subprofiles_all = parallel_pool.map(multiple_param, subset_index[chunk_index:chunk_index + configuration.MAX_FILES_SUBPROFILES])
			## Join partial profiles to the final profile of the sequence 
			if CV:							
				files_dict = concatenate_prof_CV(CV, subprofiles_all, files_dict, header, HTML_DATA)
			else:
				files_dict = concatenate_prof(subprofiles_all, files_dict, header, HTML_DATA)
			for subprofile in subprofiles_all:
				os.unlink(subprofile)
		total_length += seq_length 
		seq_lengths_all.append(seq_length)
	Ngff.close()
	log.write("ELAPSED_TIME_BLAST = {} s\n".format(time.time() - t_blast))
	log.write("TOTAL_LENGHT_ANALYZED = {} bp\n".format(total_length))
	
	
	## Protein domains module
	t_domains=time.time()
	if DOMAINS == "True":
		print("DOMAINS")
		domains_primary = NamedTemporaryFile(delete=False)
		################################################################
		#[xminimal, xmaximal, domains, seq_ids_dom] = protein_domains_pd.domain_search(QUERY, LAST_DB, CLASSIFICATION, domains_primary.name, THRESHOLD_SCORE, WIN_DOM, OVERLAP_DOM)
		protein_domains_pd.domain_search(QUERY, LAST_DB, CLASSIFICATION, domains_primary.name, THRESHOLD_SCORE, WIN_DOM, OVERLAP_DOM)
		################################################################
		domains_primary.close()
		#domains_filtering.filter_qual_dom(domains_primary.name, OUT_DOMAIN_GFF, 0.35, 0.45, 0.8, 3, 'All', "")
		[xminimal, xmaximal, domains, seq_ids_dom] = domains_filtering.filter_qual_dom(domains_primary.name, OUT_DOMAIN_GFF, 0.35, 0.45, 0.8, 3, 'All', "")
		os.unlink(domains_primary.name)
		log.write("ELAPSED_TIME_DOMAINS = {} s\n".format(time.time() - t_domains))
		#print("ELAPSED_TIME_DOMAINS = {} s".format(time.time() - t_domains))
		
		# Process individual sequences from the input file sequentially
		t_gff_vis = time.time() 
		repeats_process_dom(OUTPUT_GFF, THRESHOLD, THRESHOLD_SEGMENT, HTML_DATA, xminimal, xmaximal, domains, seq_ids_dom, CV, headers, seq_lengths_all, files_dict)
		log.write("ELAPSED_TIME_GFF_VIS = {} s\n".format(time.time() - t_gff_vis))
		
		# Prepare data for html output
		t_jbrowse=time.time()
		jbrowse_prep_dom(HTML_DATA, QUERY, OUT_DOMAIN_GFF, OUTPUT_GFF, N_GFF, total_length, JBROWSE_BIN, files_dict)	
		log.write("ELAPSED_TIME_JBROWSE_PREP = {} s\n".format(time.time() - t_jbrowse))	
	else:
		# Process individual sequences from the input file sequentially
		t_gff_vis = time.time() 
		#seq_ids_dom = []
		repeats_process(OUTPUT_GFF, THRESHOLD, THRESHOLD_SEGMENT, HTML_DATA, CV, headers, seq_lengths_all, files_dict)
		log.write("ELAPSED_TIME_GFF_VIS = {} s\n".format(time.time() - t_gff_vis))
		
		# Prepare data for html output
		t_jbrowse=time.time()
		jbrowse_prep(HTML_DATA, QUERY, OUTPUT_GFF, N_GFF, total_length, JBROWSE_BIN, files_dict)		
		log.write("ELAPSED_TIME_JBROWSE_PREP = {} s\n".format(time.time() - t_jbrowse))
	
	# Create HTML output
	t_html=time.time()
	html_output(total_length, seq_lengths_all, headers, HTML, DB_NAME, REF, REF_LINK)
	log.write("ELAPSED_TIME_HTML = {} s\n".format(time.time() - t_html))
	
	log.write("ELAPSED_TIME_PROFREP = {} s\n".format(time.time() - t_profrep))
	####################################################################
	log.close()
	####################################################################
	
	for subfasta in fasta_list:
		os.unlink(subfasta)
	
if __name__ == "__main__":
    
    # Default values(command line usage)
    HTML = configuration.HTML
    TMP = configuration.TMP
    DOMAINS_GFF = configuration.DOMAINS_GFF
    REPEATS_GFF = configuration.REPEATS_GFF
    N_REG = configuration.N_REG
    #REPEATS_TABLE = configuration.REPEATS_TABLE
    LOG_FILE = configuration.LOG_FILE
    #CLASSIFICATION = configuration.CLASSIFICATION
    #LAST_DB = configuration.LAST_DB

    
    # Command line arguments
    parser = argparse.ArgumentParser()
    
    ################ INPUTS ############################################
    parser.add_argument('-q', '--query', type=str, required=True,
						help='query sequence to be processed')
    parser.add_argument('-d', '--database', type=str,
						help='blast database of all reads')
    parser.add_argument('-a', '--annotation_tbl', type=str,
						help='clusters annotation table')
    parser.add_argument('-c', '--cls', type=str, 
						help='cls file containing reads assigned to clusters')
						
	################ BLAST parameters ##################################
    parser.add_argument('-i', '--identical', type=float, default=95,
						help='blast filtering option: sequence indentity threshold between query and mapped read from db in %')
    parser.add_argument('-l', '--align_length', type=int, default=40,
						help='blast filtering option: minimal alignment length threshold in bp')
    parser.add_argument('-m', '--max_alignments', type=int, default=10000000,
						help='blast filtering option: maximal number of alignments in the output')
    parser.add_argument('-e', '--e_value', type=str, default=1e-15,
						help='blast setting option: e-value')
    parser.add_argument('-df', '--dust_filter', type=str, default="'20 64 1'",
						help='dust low-complexity regions filtering during blast search')
    parser.add_argument('-ws', '--word_size', type=int, default=11,
						help='blast setting option: initial word size for alignment')
    parser.add_argument('-t', '--task', type=str, default="blastn",
						help='type of blast to be triggered')
    parser.add_argument('-n', '--new_db', default=False,
						help='create a new blast database')			
    parser.add_argument('-w', '--window', type=int, default=5000,
						help='window size for parallel processing')
    parser.add_argument('-o', '--overlap', type=int, default=150,
						help='overlap for parallely processed regions, set greater than read size')
									
	################ GFF PARAMETERS ####################################
    parser.add_argument('-th', '--threshold', type=int, default=5,
						help='threshold (number of hits) for report repetitive area in gff')
    parser.add_argument('-ths', '--threshold_segment', type=int, default=80,
                        help='threshold for a single segment length to be reported as repetitive reagion in gff')
                        
    ################ PROTEIN DOMAINS PARAMETERS ########################
    parser.add_argument('-pd', '--protein_domains', default=True,
						help='use module for protein domains')
    parser.add_argument('-pdb', '--protein_database', type=str,
                        help='protein domains database')
    parser.add_argument('-cs', '--classification', type=str,
                        help='protein domains classification file')
                        
	################ COVERAGE AND PREPARED DATASETS ####################
    parser.add_argument("-cv", "--coverage", type=float, 
                        help="coverage")
    parser.add_argument("-cn", "--copy_numbers", type=bool, 
                        help="convert hits to copy numbers")
    parser.add_argument("-gs", "--genome_size", type=float,
                        help="genome size")
    parser.add_argument("-id", "--db_id", type=str,
                        help="annotation database name")
    parser.add_argument("-tbl", "--datasets_tbl", type=str,
                        help="table with prepared anotation data")    
    parser.add_argument("-dbn", "--db_name", type=str,
                        help="custom database name")     
    ##################################################################### ???????????????????
    parser.add_argument("-dir","--output_dir", type=str,
						help="specify if you want to change the output directory")
	#############################################################################
    parser.add_argument("-thsc","--threshold_score", type=int, default=80,
						help="percentage of the best score in the cluster to be tolerated when assigning annotations per base")
    parser.add_argument("-wd","--win_dom", type=int, default=10000000,
						help="window to process large input sequences sequentially")
    parser.add_argument("-od","--overlap_dom", type=int, default=10000,
						help="overlap of sequences in two consecutive windows")
						
	################ OUTPUTS ###########################################
    parser.add_argument("-lg", "--log_file", type=str, default=LOG_FILE,
                  		help="path to log file")
	#parser.add_argument('-ou', '--output', type=str, default=REPEATS_TABLE,
						#help='output profile table name')
    parser.add_argument('-ouf', '--output_gff', type=str, default=REPEATS_GFF,
                        help='output gff format')
    parser.add_argument("-oug", "--domain_gff",type=str, default=DOMAINS_GFF,
						help="output domains gff format")
    parser.add_argument("-oun", "--n_gff",type=str, default=N_REG,
						help="N regions gff format")
    parser.add_argument("-hf", "--html_file", type=str, default=HTML,
                        help="output html file name")
    parser.add_argument("-hp", "--html_path", type=str, default=TMP,
                        help="path to html extra files")
	
	################ GALAXY USAGE AND JBROWSE ##########################
    parser.add_argument("-gu", "--galaxy_usage", default=False,
                        help="option for galaxy usage only")
    parser.add_argument("-td", "--tool_dir", default=False,
                  		help="tool data directory in galaxy")
    parser.add_argument("-jb", "--jbrowse_bin", type=str, default=configuration.JBROWSE_BIN,
                  		help="path to JBrowse bin directory")


    args = parser.parse_args()
    main(args)



