#!/usr/bin/env python3

import time
import configuration
from tempfile import NamedTemporaryFile
import textwrap


def filter_qual(OUTPUT_DOMAIN, FILT_DOM_GFF, TH_IDENTITY, TH_LENGTH, TH_FRAMESHIFTS):
	''' Filter gff only based on quality of alignment without domain type considering '''
	with open(OUTPUT_DOMAIN, "r") as gff_all:
		next(gff_all)
		for line in gff_all:
			attributes = line.rstrip().split("\t")[-1]
			al_identity = float(attributes.split(",")[-3].split("=")[1])
			al_length = float(attributes.split(",")[-2].split("=")[1])
			relat_frameshifts = float(attributes.split("\t")[-1].split(",")[-1].split("=")[1])
			dom_type = "-".join([attributes.split(",")[1].split("=")[1].split("/")[0], attributes.split(",")[0].split("=")[1]])
			if al_identity >= TH_IDENTITY and al_length >= TH_LENGTH and relat_frameshifts <= TH_FRAMESHIFTS :
				with open(FILT_DOM_GFF, "a") as gff_filtered:
					gff_filtered.writelines(line)
					
			
def filter_qual_dom(OUTPUT_DOMAIN, FILT_DOM_GFF, TH_IDENTITY, TH_LENGTH, TH_FRAMESHIFTS, SELECTED_DOM):
	''' Filter gff output based on domain and quality of alignment '''
	with open (FILT_DOM_GFF, "a") as gff_filtered:
		with open(OUTPUT_DOMAIN, "r") as gff_all:
			next(gff_all)
			for line in gff_all:
				attributes = line.rstrip().split("\t")[-1]
				al_identity = float(attributes.split(",")[-3].split("=")[1])
				al_length = float(attributes.split(",")[-2].split("=")[1])
				relat_frameshifts = float(attributes.split("\t")[-1].split(",")[-1].split("=")[1])
				dom_type = "-".join([attributes.split(",")[1].split("=")[1].split("/")[0], attributes.split(",")[0].split("=")[1]])
				if al_identity >= TH_IDENTITY and al_length >= TH_LENGTH and relat_frameshifts <= TH_FRAMESHIFTS and dom_type == SELECTED_DOM:
					gff_filtered.writelines(line)
					
	
def get_domains_protseq(QUERY, FILT_DOM_GFF, DOMAIN_PROT_SEQ):
	''' Get the original nucleic sequence and protein sequence of the reported domains regions '''
	with open(FILT_DOM_GFF, "r") as filt_gff:
		#next(filt_gff)
		for line in filt_gff: 
			start = int(line.rstrip().split("\t")[3])
			end = int(line.rstrip().split("\t")[4])
			attributes = line.rstrip().split("\t")[8]
			dom = attributes.split(",")[0].split("=")[1]
			dom_class = "{}/{}".format(attributes.split(",")[1].split("=")[1], attributes.split(",")[2].split("=")[1])
			seq_id = line.rstrip().split("\t")[0]
			prot_seq = line.rstrip().split("\t")[8].split(",")[3].split("=")[1]
			header_prot_seq = ">{}:{}-{} {} {}".format(seq_id, start, end, dom, dom_class)
			with open(DOMAIN_PROT_SEQ, "a") as dom_prot_file:
				dom_prot_file.write("{}\n{}\n".format(header_prot_seq, textwrap.fill(prot_seq, configuration.FASTA_LINE)))

					
def filter_params(reference_seq, alignment_seq, protein_len):
	''' Calculate basic statistics of the quality of alignment '''
	num_ident = 0
	count_frm = 0
	alignment_len = 0
	for i,j in zip(reference_seq, alignment_seq):
		if i==j:
			num_ident += 1
		if j == "/" or j == "\\":
			count_frm += 1
		if i.isalpha():
			alignment_len += 1
	relat_align_len = round(alignment_len/protein_len, 3) 
	align_identity = round(num_ident/len(alignment_seq), 2)
	relat_frameshifts = round(count_frm/(len(alignment_seq)/100),2)
	return align_identity, relat_align_len, relat_frameshifts	


def main(args):
	
	t = time.time()
	
	QUERY = args.query
	OUTPUT_DOMAIN = args.domain_gff
	DOMAIN_PROT_SEQ = args.domains_prot_seq
	TH_IDENTITY = args.th_identity
	TH_LENGTH = args.th_length 
	TH_FRAMESHIFTS = args.frameshifts
	FILT_DOM_GFF = args.domains_filtered
	SELECTED_DOM = args.selected_dom
	
	if SELECTED_DOM != "All":
		filter_qual_dom(OUTPUT_DOMAIN, FILT_DOM_GFF, TH_IDENTITY, TH_LENGTH, TH_FRAMESHIFTS, SELECTED_DOM)
	else:
		filter_qual(OUTPUT_DOMAIN, FILT_DOM_GFF, TH_IDENTITY, TH_LENGTH, TH_FRAMESHIFTS)
	get_domains_protseq(QUERY, FILT_DOM_GFF, DOMAIN_PROT_SEQ)
	
	
	print("ELAPSED_TIME_DOMAINS = {} s".format(time.time() - t))
	
if __name__ == "__main__":
	import argparse

	DOMAINS_GFF = configuration.DOMAINS_GFF
	DOM_PROT_SEQ = configuration.DOM_PROT_SEQ
	FILT_DOM_GFF = configuration.FILT_DOM_GFF

	parser = argparse.ArgumentParser()
	parser.add_argument("-q","--query",type=str, required=True,
						help="query sequence to find protein domains in")
	parser.add_argument("-oug", "--domain_gff",type=str, default=DOMAINS_GFF,
						help="output domains gff format")
	parser.add_argument("-ouf","--domains_filtered",type=str, default=FILT_DOM_GFF,
						help="filtered domains gff format") 
	parser.add_argument("-dps","--domains_prot_seq",type=str, default=DOM_PROT_SEQ,
						help="file containg domains protein sequences")
	parser.add_argument("-thl","--th_length",type=float, default= 0.8,
						help="length threshold for alignment")
	parser.add_argument("-thi","--th_identity",type=float, default= 0.35,
						help="identity threshold for alignment")
	parser.add_argument("-fr","--frameshifts",type=int, default=1,
						help="frameshifts tolerance threshold per 100 bp")
	parser.add_argument("-sd","--selected_dom",type=str, default="All",
						help="filter output domains based on the domain type")
	
	args = parser.parse_args()
	main(args)
