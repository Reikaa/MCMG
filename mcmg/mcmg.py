'''
	Markov Chain Music Generator
	
'''


class Note:
	def __init__(self, step, octave, alter = 0):
		self.step = step
		self.octave = int(octave)
		self.alter = int(alter) # but could be decimal

	def __repr__(self):
		accidental = None
		if (self.alter >= 0):
			accidental = '#' * self.alter
		else:
			accidental = 'b' * (-1 * self.alter)

		return self.step + accidental + str(self.octave)

	def midi(self): # ...note number
		offsets = {'C':0, 'D':2, 'E':4, 'F':5, 'G':7, 'A':9, 'B':11}
		num = (self.octave + 1) * 12 
		num += offsets[self.step] 
		num += self.alter
		return num

	def __hash__(self):
		return self.midi() # hash(int) returns just integer itself
	
	def __cmp__(self, other): 
		'''self > other if 'self' note is of higher frequency than 'other' note'''
		if (not isinstance(other, Note)):
			return NotImplemented # Correct return value for comparing objects of different types
		return self.midi() - other.midi()


import xml.etree.ElementTree as ET
class MusicXml:
	def _type_to_div(self, type, dotted, divisions_per_quarter):
		''' Maps from note duration names (quarter, whole, etc.) to MusicXML divisions '''
		mapping = {
			'whole':	('multiply', 4),
			'half':		('multiply', 2),
			'quarter':	('multiply', 1),
			'eighth':	('divide', 2),
			'16th':		('divide', 4),
			'32nd':		('divide', 8)
			}
		
		if (type not in mapping):
			raise RuntimeError('Unsupported note duration type "%s"' % (type))

		if (mapping[type][0] == 'divide' and divisions_per_quarter % mapping[type][1] != 0):
			raise RuntimeError('%s notes are not representable if there are %d divisions per quarter note' % (type, divisions_per_quarter))

		div = divisions_per_quarter * mapping[type][1] if mapping[type][0] == 'multiply' else divisions_per_quarter / mapping[type][1]

		if (dotted == True and div % 2 != 0):
			raise RuntimeError('Dotted %s is not representable if there are %d divisions per quarter note' % (type, divisions_per_quarter))
		
		if (dotted == True):
			div = div * 3 / 2

		return div

	def _div_to_types(self, div, divisions_per_quarter):
		''' Maps MusicXML divisions to note duration names (quarter, whole, etc.) '''
		if (div > 4 * divisions_per_quarter or div < 1):
			raise RuntimeError('Divisions argument out of range [4*divisions_per_quarter, 1]')
		
		d = divisions_per_quarter
		mapping = {
			d/8.0 :	'32nd',
			d/4.0:	'16th',
			d/2.0:	'eighth',
			d:		'quarter',
			2*d:	'half',
			4*d:	'whole'
			}

		if (div in mapping):
			return [{'type':mapping[div], 'dotted':False}]

		if (div % 3 == 0 and div*2/3 in mapping):
			return [{'type':mapping[div*2/3], 'dotted':True}]

		# "Greedy Tie" - note needs to be broken down into several tied notes
		div_i = div
		tie = []
		while(div_i > 0):
			for i in reversed(range(1, div_i + 1)):
				if (i in mapping):
					tie.append({'type':mapping[i], 'dotted':False})
					div_i -= i
					break
				if (i % 3 == 0 and i*2/3 in mapping):
					tie.append({'type':mapping[i*2/3], 'dotted':True})
					div_i -= i
					break

		return tie

	
	def _determine_divisions(self, dur_seq):
		''' Calculates optimum value for <divisions></divisions> MusicXML tag '''
		mapping = {
			'whole':	1,
			'half':		2,
			'quarter':	4,
			'eighth':	8,
			'16th':		16,
			'32nd':		32
			}

		shortest_duration_denominator = 0
		for dur in dur_seq:
			if (mapping[dur['type']] > shortest_duration_denominator):
				shortest_duration_denominator = mapping[dur['type']]

		return max(shortest_duration_denominator/4, 1)
	
	def _add_attributes(self, measure, divisions_per_quarter, beats, beat_type):
		''' Adds <attributes> tag to specified <measure> MusicXML tag '''
		addchild = ET.SubElement
		attributes = addchild(measure, 'attributes')

		addchild(attributes, 'divisions').text = str(divisions_per_quarter)
		addchild(addchild(attributes, 'key'), 'fifth').text = '0'
		time = addchild(attributes, 'time')
		addchild(time, 'beats').text = str(beats)
		addchild(time, 'beat-type').text = str(beat_type)

		clef = addchild(attributes, 'clef')
		addchild(clef, 'sign').text = 'G'
		addchild(clef, 'line').text = '2'
	

	def _add_note_xml(self, measure, pitch, div, type, dotted, tie_start, tie_end):
		''' Adds MusicXML code for one note '''
		#print 'Add note: %s div=%d type=%s dotted=%s tie_start=%s tie_end=%s' % (str(pitch), div, type, dotted, tie_start, tie_end)
		addchild = ET.SubElement

		note_tag = addchild(measure, 'note')
		pitch_tag = addchild(note_tag, 'pitch')
		addchild(pitch_tag, 'step').text = pitch.step
		addchild(pitch_tag, 'octave').text = str(pitch.octave)
		if (pitch.alter != 0): 
			addchild(pitch_tag, 'alter').text = str(pitch.alter)

		addchild(note_tag, 'duration').text = str(div)
		if (tie_end == True):
			tie = addchild(note_tag, 'tie')
			tie.set('type', 'stop')
		if (tie_start == True):
			tie = addchild(note_tag, 'tie')
			tie.set('type', 'start')
		addchild(note_tag, 'type').text = type
		if (dotted == True):
			addchild(note_tag, 'dot')

		notations_tag = None
		if (tie_start == True or tie_end == True):
			notations_tag = addchild(note_tag, 'notations')
		if (tie_end == True):
			tied = addchild(notations_tag, 'tied')
			tied.set('type', 'stop')
		if (tie_start == True):
			tied = addchild(notations_tag, 'tied')
			tied.set('type', 'start')

	def write_mxl(self, note_seq, dur_seq, part_name='Artificial'):
		''' Writes given note and durations sequence (in "quarter, whole, etc." form) into MusicXML file '''
		if (len(note_seq) != len(dur_seq)):
			raise RuntimeError('Notes sequence and Durations sequence must be of the same length!')

		root = ET.Element('score-partwise')
		root.set('version', '3.0')
	
		addchild = ET.SubElement

		part_list = addchild(root, 'part-list')

		score_part = addchild(part_list, 'score-part')
		score_part.set('id', 'P1')

		addchild(score_part, 'part-name').text = part_name

		part = addchild(root, 'part')
		part.set('id', 'P1')

		note_seq = list(reversed(note_seq))
		dur_seq = [{'type':T, 'dotted':False} for T in list(reversed(dur_seq))] # convert to type paired with dottedness
		BEATS = 4 # hardcoded for now
		BEAT_TYPE = 4
		DIVISIONS_PER_QUARTER = self._determine_divisions(dur_seq)
		DIVISIONS_PER_MEASURE = 4 * DIVISIONS_PER_QUARTER * BEATS / BEAT_TYPE
		running_sum = DIVISIONS_PER_MEASURE
		#print '<divisions>%d</divisions> per_measure=%d' % (DIVISIONS_PER_QUARTER, DIVISIONS_PER_MEASURE)
		tie_start_monitor = 0 # is this called a 'monitor' really?
		tie_end_monitor = 0
		measure = None
		measure_num = 1
		while(len(note_seq) > 0):
			if (running_sum == DIVISIONS_PER_MEASURE):
				# create new measure
				#print 'MEASURE'
				measure = addchild(part, 'measure')
				measure.set('number', str(measure_num))
				if (measure_num == 1):
					self._add_attributes(measure, DIVISIONS_PER_QUARTER, BEATS, BEAT_TYPE)
				measure_num += 1
				running_sum = 0

			N = note_seq.pop()
			T = dur_seq.pop()
			D = self._type_to_div(T['type'], T['dotted'], DIVISIONS_PER_QUARTER)

			if (DIVISIONS_PER_MEASURE - running_sum < D):
				D_orig = D
				D = DIVISIONS_PER_MEASURE - running_sum
				D_remainder = D_orig - D
				T_remainder = self._div_to_types(D_remainder, DIVISIONS_PER_QUARTER)
				for T_rem in reversed(T_remainder):
					note_seq.append(N)
					dur_seq.append(T_rem)
					tie_start_monitor += 1

			Ts = self._div_to_types(D, DIVISIONS_PER_QUARTER)
			T = Ts[0]
			del Ts[0]
			D = self._type_to_div(T['type'], T['dotted'], DIVISIONS_PER_QUARTER)
			for T_tied in reversed(Ts):
				note_seq.append(N)
				dur_seq.append(T_tied)
				tie_start_monitor += 1

			tie_end = False
			tie_start = False
			if (tie_end_monitor > 0):
				tie_end = True
				tie_end_monitor -= 1
			if (tie_start_monitor > 0):
				tie_start = True
				tie_start_monitor -= 1
				tie_end_monitor += 1

			self._add_note_xml(measure, N, D, T['type'], T['dotted'], tie_start, tie_end)
			running_sum += D

		filename = 'generated.xml'
		ET.ElementTree(root).write(filename)
		print 'Music written to ' + filename

if (__name__ == '__main__'):
	import sys
	
	pid = None
	training_notes_limit = None
	music_xml_filename = 'D:\Projects\MCMG\MusicXML\The_dance_of_victory-Eluveitie\lg-155582393382959147.xml'
	#music_xml_filename = 'D:\Projects\MCMG\MusicXML\Metallica_The_Unforgiven_solo_only\lg-893624106868431893.xml'

	#music_xml_filename = 'D:\Projects\MCMG\MusicXML\Yesterday_-_The_Beatles\lg-554418414057536766.xml'
	#music_xml_filename = 'D:\Projects\MCMG\MusicXML\An_cluinn_thu_mi_mo_nighean_donn\lg-337877602013703783.xml'
	
	#music_xml_filename = 'D:\Projects\MCMG\MusicXML\Galway_Celtic_tunes\lg-584039090251899670.xml'

	#music_xml_filename = 'D:\Projects\MCMG\MusicXML\Carol_of_the_Bells_Ukrainian_Bell_Carol\lg-263263748897903147.xml'
	#pid = 'P1'

	#music_xml_filename = 'D:\Projects\MCMG\MusicXML\Sweet_Child_of_mine\lg-515878348846837448.xml'
	#pid = 'P2'

	#music_xml_filename = 'D:\Projects\MCMG\MusicXML\Nemo_-_Nightwish_String_Quartet\lg-745000545513312548.xml'
	#pid = 'P2'
	#training_notes_limit = 45

	#music_xml_filename = 'D:\Projects\MCMG\MusicXML\Garry_Porch_of_Avernish_Scottish\lg-696634382210268678.xml'
	#pid = 'P1'


	#######################
	import xml.etree.ElementTree as ET
	tree = ET.parse(music_xml_filename)
	root = tree.getroot()

	# TODO a "choose part" dialog
	# Choose a part to train on:
	# [1] (P1) Piano
	# [2] (P2) Violin
	
	part = None
	if (pid == None):
		part = root.find('part')
	else:
		part = root.find("./part[@id='%s']" % pid)

	part_id = part.get('id')
	part_name = root.find("./part-list/score-part[@id='%s']" % part_id).find('part-name').text
	part_name = '' if part_name == None else part_name

	print 'Reading from file "%s"' % music_xml_filename
	print 'Training on part "%s" (%s)' % (part_name.encode('UTF-8'), part_id)


	note_sequence = []
	durations_sequence = []
	#print 'Training on first %d notes of part "%s":' % (PRINT_NOTES, part_name)
	for note in part.iter('note'):
		pitch_element = note.find('pitch')
		if (pitch_element == None):
			# a rest
			print 'Skipping a rest'
			continue

		step = pitch_element.find('step').text
		octave = note.find('pitch').find('octave').text
		
		alter = note.find('pitch').find('alter')
		if (alter == None): alter = 0
		else: alter = int(alter.text)
		
		n = Note(step, octave, alter)
		note_sequence.append(n)

		type = note.find('type').text
		durations_sequence.append(type)

		#print n, '\t', type

	
	if (training_notes_limit is not None):
		note_sequence = note_sequence[0:training_notes_limit]
		print 'Applying limit on training notes count: %d' % (training_notes_limit)


	# parameterized implementation of Markov chain
	import Markov
	MARKOV_DEGREE = 4
	noteChain = Markov.MarkovChainN(MARKOV_DEGREE)
	noteChain.train(note_sequence)
	print '======= Notes Markov Chain ======='
	print noteChain

	durChain = Markov.MarkovChainN(MARKOV_DEGREE)
	durChain.train(durations_sequence)
	print '======= Durations Markov Chain ======='
	print durChain

	#note_seq = noteChain.generate_at_least(20)
	note_seq = noteChain.generate()
	dur_seq = durChain.generate_length(len(note_seq))

	mx = MusicXml()		
	print '==========================='
	mx.write_mxl(note_seq, dur_seq, 'Markov chain degree ' + str(MARKOV_DEGREE))


	#ch = MarkovChain()
	#words = 'mast tame same teams team meat steam stem'.split(' ')
	#[ch.train(x) for x in words]
	#print ch


# rests are not supported
# dotted notes in training scores are read as non-dotted (but dotted notes can be generated)
# tied notes in training scores are read as separate (but tied notes can be generated)
