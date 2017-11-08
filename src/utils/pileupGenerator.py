import argparse
import pysam
from pysam import VariantFile
from bitarray import bitarray
from sys import getsizeof
import multiprocessing
from multiprocessing import Process, Pool, TimeoutError, Array, Manager
from PIL import Image
import random
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import time
from timeit import default_timer as timer
import sys
import os
import SamPileupBMP
"""
This program takes an alignment file (bam) and a reference file
to create a sparse bitmap representation of the pileup. It uses
pysam's pileup method and encodes each base in pileup to 6 binary
bits. It creates a large binary sparse matrix too.
"""
allVariantRecord = {}

def getClassForGenotype(gtField):
    if gtField[0] == gtField[-1]:
        if gtField[0] == '0':
            return 0 #homozygous reference
        else:
            return 2 #homozygous alt
    else:
        return 1 #heterozygous

def getGTField(rec):
    return str(rec).rstrip().split('\t')[-1].split(':')[0].replace('/', '|').replace('\\', '|').split('|')

def populateRecordDictionary(vcf_region, vcfFile, qualityCutoff=60):
    vcf_in = VariantFile(vcfFile)
    for rec in vcf_in.fetch(region="chr"+vcf_region):
        gtField = getGTField(rec)

        genotypeClass = getClassForGenotype(gtField)
        if genotypeClass != 0 and rec.qual is not None and rec.qual > qualityCutoff:
            alleles = rec.alleles
            longestAllele = 0

            for i in gtField: # find length of longest allele that was called as a variant
                length = len(alleles[int(i)])

                if length > longestAllele:
                    longestAllele = length

            for i in range(rec.start, rec.stop):
                allVariantRecord[i] = (genotypeClass,longestAllele)


def getLabel(start, end):
    labelStr = ''
    variantLengths = dict()

    count = 0
    for j,i in enumerate(range(start, end)):
        if i in allVariantRecord.keys():
            labelStr += str(allVariantRecord[i][0])

            if count == 0:
                variantLengths[j] = int(allVariantRecord[i][1])
                count = allVariantRecord[i][1] - 1
            else:
                count -= 1
        else:
            labelStr += str(0)
    return labelStr,variantLengths


def generatePileupBasedonVCF(vcf_region, bamFile, refFile, vcfFile, output_dir, window_size, qualityCutoff=60):
    cnt = 0
    start_timer = timer()
    populateRecordDictionary(vcf_region, vcfFile)
    smry = open(output_dir + 'summary' + '-' + vcf_region + ".csv", 'w')

    for rec in VariantFile(vcfFile).fetch(region="chr"+vcf_region+":77131-90000"):
        if rec.qual is not None and rec.qual > qualityCutoff and getClassForGenotype(getGTField(rec)) != '0':
            start = rec.pos - window_size - 1
            end = rec.pos + window_size
            labelString,variantLengths = getLabel(start, end)
            filename = output_dir + rec.chrom + "-" + str(rec.pos)

            p = SamPileupBMP.PileUpGenerator(bamFile, refFile)
            outputLabelString = p.generatePileup(chromosome=vcf_region, position=rec.pos - 1, flankLength=window_size, outputFilename=filename, label=labelString, variantLengths=variantLengths)

            cnt += 1
            if cnt % 1000 == 0:
                end_timer = timer()
                print(str(cnt) + " Records done", file=sys.stderr)
                print("TIME elapsed "+ str(end_timer - start_timer), file=sys.stderr)
            smry.write(os.path.abspath(filename) + ".bmp," + str(outputLabelString)+'\n')

            if cnt > 30:
                break


if __name__ == '__main__':
    '''
    Processes arguments and performs tasks to generate the pileup.
    '''
    parser = argparse.ArgumentParser()
    parser.register("type", "bool", lambda v: v.lower() == "true")
    parser.add_argument(
        "--bam",
        type=str,
        required = True,
        help="BAM file with alignments."
    )
    parser.add_argument(
        "--ref",
        type=str,
        required=True,
        help="Reference corresponding to the BAM file."
    )
    parser.add_argument(
        "--vcf",
        type=str,
        required=False,
        help="VCF file containing SNPs and SVs."
    )
    parser.add_argument(
        "--region",
        type = str,
        default = "chr3",
        help="Site region. Ex: chr3"
    )
    parser.add_argument(
        "--vcf_region",
        type=str,
        default="3",
        help="Site region. Ex: chr3"
    )
    parser.add_argument(
        "--coverage",
        type=int,
        default=50,
        help="Read coverage, default is 50x."
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="output/",
        help="Name of output directory"
    )
    parser.add_argument(
        "--window_size",
        type=int,
        default=100,
        help="Window size of pileup."
    )
    FLAGS, unparsed = parser.parse_known_args()
    generatePileupBasedonVCF(FLAGS.vcf_region, FLAGS.bam, FLAGS.ref, FLAGS.vcf, FLAGS.output_dir, FLAGS.window_size)


# example usage
# python3 "deePore/src/utils/pileupGenerator.py" --bam "deePore/data/chr3_200k.bam" --ref "deePore/data/chr3.fa" --vcf "deePore/data/NA12878_S1.genome.vcf.gz" --region "chr3" --output_dir "deePore/data/test2/" --window_size 25 >deePore/data/stdout_final.txt
