# -*- coding: utf-8 -*-
"""
Modified by Joan Mas Colomer,
from the code written by Nikolay Asmolovskiy.

Copyright (c) 2015 by Nikolay Asmolovskiy

Some rights reserved.

Copyright (c) 2019, ISAE
All rights reserved.
Copyright (c) 2019, Joan Mas Colomer
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.

    * Redistributions in binary form must reproduce the above
      copyright notice, this list of conditions and the following
      disclaimer in the documentation and/or other materials provided
      with the distribution.

    * The names of the contributors may not be used to endorse or
      promote products derived from this software without specific
      prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""

import cmath

#Modified by Joan Mas Colomer Feb 18, 2019
CONST_VALID_REQUESTS = ['ACCELERATION', 'DISPLACEMENTS', 'MPCF',
                        'SPCF', 'ELEMENT FORCES', 'ELEMENT STRAINS', 'ELEMENT STRESSES']


def dispatch_parse(output, data_chunks):
    if output == 'MAGNITUDE-PHASE' or output == 'REAL-IMAGINARY':
        num = int(len(data_chunks) / 2)
        if len(data_chunks) % 2 != 0:
            raise ValueError('Wrong number of chunks!', 'Output: %s, num of chunks: %d' % (output, len(data_chunks)))
    else:
        num = len(data_chunks)

    if output == 'MAGNITUDE-PHASE':
        return [data_chunks[i]*cmath.exp(1j*data_chunks[i+num]*cmath.pi/180.0) for i in range(num)]
    elif output == 'REAL-IMAGINARY':
        return [data_chunks[i] + 1j*data_chunks[i+num] for i in range(num)]
    else:
        return [data_chunks[i] for i in range(num)]


class PchParser:
    def reset_current_frame(self):
        self.cur_data_chunks = []
        self.is_frequency_response = False
        self.output_sort = 0
        self.cur_subcase = 0
        self.cur_output = 0
        self.current_frequency = 0
        self.cur_entity_id = 0
        self.cur_entity_type_id = 0
        #Modified by Joan Mas Colomer Mar 8 2019
        self.cur_mode = 0

    def __init__(self, filename):
        # define the dictionary
        self.parsed_data = {'FREQUENCY': {}, 'SUBCASES': set()}
        for request in CONST_VALID_REQUESTS:
            self.parsed_data[request] = {}

        #Initialize list of modal requests (#Modified by Joan Mas Colomer Mar 8 2019)
        self.modal_requests = []

        # initiate current frame
        self.reset_current_frame()

        is_header = True

        # start reading
        with open(filename, 'r') as pch:
            # read only first 72 characters from the punch file
            for line in pch:
                line = line[0:72]

                # reset all variables
                if line.startswith('$TITLE   ='):
                    is_header = False
                    # insert the last frame remaining in memory
                    self.insert_current_frame()
                    # reset the frame
                    self.reset_current_frame()

                # skip everything before TITLE
                if is_header:
                    continue

                # parse the subcase
                if line.startswith('$SUBCASE ID ='):
                    self.cur_subcase = int(line[13:].strip())
                    self.parsed_data['SUBCASES'].add(self.cur_subcase)

                #Modified by Joan Mas Colomer Mar 8 2019
                if line.startswith('$EIGENVALUE ='):
                    self.cur_mode = int(line[36:].strip())

                # identify NASTRAN request
                if line.startswith('$DISPLACEMENTS'):
                    self.cur_request = 'DISPLACEMENTS'
                elif line.startswith('$ACCELERATION'):
                    self.cur_request = 'ACCELERATION'
                elif line.startswith('$MPCF'):
                    self.cur_request = 'MPCF'
                elif line.startswith('$SPCF'):
                    self.cur_request = 'SPCF'
                elif line.startswith('$ELEMENT FORCES'):
                    self.cur_request = 'ELEMENT FORCES'
                elif line.startswith('$ELEMENT STRAINS'):
                    self.cur_request = 'ELEMENT STRAINS'
                #Modified by Joan Mas Colomer Jan 30, 2019
                elif line.startswith('$ELEMENT STRESSES'):
                    self.cur_request = 'ELEMENT STRESSES'
                #Modified by Joan Mas Colomer Mar 8, 2019
                elif line.startswith('$EIGENVALUE') and self.cur_mode > 0:
                    self.cur_request = 'EIGENVECTOR'+'-'+str(self.cur_mode)
                    self.parsed_data[self.cur_request] = {}
                    self.modal_requests.append(self.cur_request)

                # identify output type
                if line.startswith('$REAL-IMAGINARY OUTPUT'):
                    self.cur_output = 'REAL-IMAGINARY'
                elif line.startswith('$MAGNITUDE-PHASE OUTPUT'):
                    self.cur_output = 'MAGNITUDE-PHASE'
                elif line.startswith('REAL OUTPUT'):
                    self.cur_output = 'REAL'

                # parse of frequency response results
                if line.find('IDENTIFIED BY FREQUENCY') != -1:
                    self.is_frequency_response = True
                    self.output_sort = 2
                elif line.find('$FREQUENCY =') != -1:
                    self.is_frequency_response = True
                    self.output_sort = 1

                # parse entity id
                if line.startswith('$POINT ID ='):
                    self.cur_entity_id = int(line[11:23].strip())
                elif line.startswith('$ELEMENT ID ='):
                    self.cur_entity_id = int(line[13:23].strip())
                elif line.startswith('$FREQUENCY = '):
                    self.current_frequency = float(line[12:28].strip())

                # parse element type
                if line.startswith('$ELEMENT TYPE ='):
                    self.cur_entity_type_id = int(line[15:27].strip())

                # ignore other comments
                if line.startswith('$'):
                    continue

                # check if everything ok
                self.validate()

                # start data parsing
                line = line.replace('G', ' ')
                if line.startswith('-CONT-'):
                    line = line.replace('-CONT-', '')
                    self.cur_data_chunks += [float(_) for _ in line.split()]
                else:
                    # insert the last frame
                    self.insert_current_frame()

                    # update the last frame with a new data
                    self.cur_data_chunks = [float(_) for _ in line.split()]

            # last block remaining in memory
            self.insert_current_frame()

    def validate(self):
        #Modified by Joan Mas Colomer Mar 8 2019
        if (self.cur_request not in CONST_VALID_REQUESTS) and (self.cur_request not in self.modal_requests):
            raise NotImplementedError("Request %s is not implemented", self.cur_request)

        if self.cur_request == 'ELEMENT FORCES' and self.cur_entity_type_id not in [12, 102]:
            raise NotImplementedError("Element forces parser is implemented only for CELAS2 and CBUSH elements!")

    def insert_current_frame(self):
        # last block remaining in memory
        if len(self.cur_data_chunks) > 0:
            # ensure that subcase is allocated in the dataset
            if self.cur_subcase not in self.parsed_data[self.cur_request]:
                self.parsed_data[self.cur_request][self.cur_subcase] = {}
                self.parsed_data['FREQUENCY'][self.cur_subcase] = {}

            values = dispatch_parse(self.cur_output, self.cur_data_chunks[1:])
            if self.is_frequency_response:
                # incremented by frequency, entity is given
                if self.output_sort == 2:
                    self.current_frequency = self.cur_data_chunks[0]
                # incremented by entity, frequency is given
                elif self.output_sort == 1:
                    self.cur_entity_id = int(self.cur_data_chunks[0])

                # insert frequency in the database
                if self.current_frequency not in self.parsed_data['FREQUENCY'][self.cur_subcase]:
                    self.parsed_data['FREQUENCY'][self.cur_subcase][self.current_frequency] = \
                        len(self.parsed_data['FREQUENCY'][self.cur_subcase])

                # ensure that dictionary for the entity exists
                if self.cur_entity_id not in self.parsed_data[self.cur_request][self.cur_subcase]:
                    self.parsed_data[self.cur_request][self.cur_subcase][self.cur_entity_id] = []

                self.parsed_data[self.cur_request][self.cur_subcase][self.cur_entity_id].append(values)
            else:
                self.cur_entity_id = int(self.cur_data_chunks[0])
                self.parsed_data[self.cur_request][self.cur_subcase][self.cur_entity_id] = values

    def health_check(self):
        frequency_steps = []
        for subcase in self.parsed_data['SUBCASES']:
            frequency_steps.append(len(self.parsed_data['FREQUENCY'][subcase]))
        assert min(frequency_steps) == max(frequency_steps)

    def get_subcases(self):
        return sorted(self.parsed_data['SUBCASES'])

    def __get_data_per_request(self, request, subcase):
        self.health_check()
        if subcase in self.parsed_data[request]:
            return self.parsed_data[request][subcase]
        else:
            raise KeyError('%s data for subase %d is not found' % (request, subcase))

    def get_accelerations(self, subcase):
        return self.__get_data_per_request('ACCELERATION', subcase)

    def get_displacements(self, subcase):
        return self.__get_data_per_request('DISPLACEMENTS', subcase)

    def get_mpcf(self, subcase):
        return self.__get_data_per_request('MPCF', subcase)

    def get_spcf(self, subcase):
        return self.__get_data_per_request('SPCF', subcase)

    def get_forces(self, subcase):
        return self.__get_data_per_request('ELEMENT FORCES', subcase)

    #Modified by Joan Mas Colomer Jan 30, 2019
    def get_stresses(self, subcase):
        return self.__get_data_per_request('ELEMENT STRESSES', subcase)

    #Modified by Joan Mas Colomer Mar 8, 2019
    def get_eigenvectors(self, subcase):
        eigenvectors = {}
        for request in self.modal_requests:
            eigenvectors[request] = self.__get_data_per_request(
                request, subcase)
        return eigenvectors

    def get_frequencies(self, subcase):
        return sorted(self.parsed_data['FREQUENCY'][subcase])
