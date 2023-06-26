import pickle
import string
import time

import gensim
import matplotlib.pyplot as plt
import nltk
import numpy as np
import numpy.linalg
from nltk.corpus import stopwords
from nltk import word_tokenize
from nltk.data import find
from sentence_transformers import SentenceTransformer
import gensim.downloader as api

word2vec_sample = str(find('models/word2vec_sample/pruned.word2vec.txt'))
w2v = gensim.models.KeyedVectors.load_word2vec_format(word2vec_sample, binary=False)
#w2v = api.load("glove-twitter-25")
sentence_transformer = SentenceTransformer('all-MiniLM-L6-v2')
print(len(w2v))
print(len(w2v["banana"]))

def evaluation_function(response, answer, params):
    """
    Function used to evaluate a student response.
    ---
    The handler function passes three arguments to evaluation_function():

    - `response` which are the answers provided by the student.
    - `answer` which are the correct answers to compare against.
    - `params` which are any extra parameters that may be useful,
        e.g., error tolerances.

    The output of this function is what is returned as the API response
    and therefore must be JSON-encodable. It must also conform to the
    response schema.

    Any standard python library may be used, as well as any package
    available on pip (provided it is added to requirements.txt).

    The way you wish to structure you code (all in this function, or 
    split into many) is entirely     up to you. All that matters are the
    return types and that evaluation_function() is the main function used 
    to output the evaluation response.
    """
    start_time = time.time()

    # params of the form {'keystrings': ['keystring1', 'keystring2', ...]}
    # keystring of the form {'string':..., 'exact_match:False', 'should_contain:True', 'custom_feedback:None, 'mode:string'}
    if params is not None and "keystrings" in params:
        keystrings = params["keystrings"]
        problematic_keystring = None
        keystring_scores = []
        response_tokens = preprocess_tokens(response)
        for keystring_object in keystrings:
            # Unpack keystring object
            keystring = keystring_object['string']
            exact_match = keystring_object['exact_match'] if 'exact_match' in keystring_object else False
            should_contain = keystring_object['should_contain'] if 'should_contain' in keystring_object else True
            custom_feedback = keystring_object['custom_feedback'] if 'custom_feedback' in keystring_object else None
            mode = keystring_object['mode'] if 'mode' in keystring_object else 'auto'
            similarity_function = get_similarity_function_by_mode(mode)
            keystring_tokens = preprocess_tokens(keystring)

            # Sliding window matching
            window_size = len(keystring_tokens)
            i = 0
            max_score = 0
            while i + window_size <= len(response_tokens):
                response_substring = " ".join(response_tokens[i:i + window_size])
                max_score = max(max_score, similarity_function(response_substring, keystring))
                i += 1
            keystring_scores.append((keystring, max_score))

            threshold = 0.75
            if exact_match is True:
                threshold = 0.99

            if should_contain is True and max_score < threshold and problematic_keystring is None:
                problematic_keystring = keystring
                feedback = f"Cannot determine if the answer is correct. Please provide more information about '{problematic_keystring}'"

            if should_contain is False and max_score > threshold and problematic_keystring is None:
                problematic_keystring = keystring
                feedback = f"Cannot determine if the answer is correct. Identified '{problematic_keystring}' in the answer, which was not expected."

            if custom_feedback is not None:
                feedback = f"Cannot determine if the answer is correct. {custom_feedback}"

        if problematic_keystring is not None:
            return {
                "is_correct": False,
                "result": {
                    "response": response,
                    "processing_time": time.time() - start_time,
                    "keystring-scores": keystring_scores
                },
                "feedback": feedback
            }

    mode = 'w2v'
    if len(preprocess_tokens(response)) >= 10:
        mode = 'transformer'

    if params is not None and "mode" in params:
        mode = params["mode"]
    similarity_function = get_similarity_function_by_mode(mode)
    w2v_similarity = similarity_function(response, answer)

    if w2v_similarity > 0.75:
        return {
            "is_correct": True,
            "result": {
                "response": response,
                "processing_time": time.time() - start_time,
                "method": "w2v",
                "similarity_value": w2v_similarity
            },
            "feedback": f"Confidence: {'%.3f'%(w2v_similarity)}%"
        }

    else:
        similarity, response_scores, answer_scores = sentence_similarity(response, answer)
        dif = 0
        word = None
        for (resp_score, ans_score) in zip(response_scores, answer_scores):
            if resp_score[0] - ans_score[0] > dif:
                dif = resp_score[0] - ans_score[0]
                word = resp_score[1]

        return {
            "is_correct": False,
            "result": {
                "response": response,
                "processing_time": time.time() - start_time,
                "method": "BOW vector similarity",
                "similarity_value": w2v_similarity,
                "BOW_similarity_value": similarity,
                "problematic_word": word
            },
            "feedback": f"Cannot determine if the answer is correct ({'%.3f'%(w2v_similarity)}% similarity). {f'Please provide more information about {word}' if word is not None else ''}"
        }


def word_information_content(word, blen, freqs):
    if word not in freqs:
        f = 0
    else:
        f = freqs[word]
    return 1 - (np.log(f + 1)) / (np.log(blen + 1))


def word_similarity(word1, word2, w2v):
    if word1 == word2:
        return 1
    if not w2v.has_index_for(word1) or not w2v.has_index_for(word2):
        return 0
    return w2v.similarity(word1, word2)


def sentence_similarity(response: str, answer: str):
    response = response.lower()
    answer = answer.lower()
    for punc in string.punctuation:
        response = response.replace(punc, ' ')
        answer = answer.replace(punc, ' ')
    response_words = response.split()
    answer_words = answer.split()
    all_words = list(set((response_words + answer_words)))

    with open('brown_length', 'rb') as fp:
        blen = pickle.load(fp)
    with open('word_freqs', 'rb') as fp:
        freqs = pickle.load(fp)

    def sencence_scores(common_words, sentence):
        scores = []
        for word in common_words:
            best_similarity = -1
            best_word = word
            for other_word in sentence:
                similarity = word_similarity(word, other_word, w2v)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_word = other_word
            scores.append(
                (best_similarity * word_information_content(word, blen, freqs) * word_information_content(best_word,
                                                                                                          blen, freqs),
                 word))
        return scores

    response_scores = sencence_scores(all_words, response_words)
    answer_scores = sencence_scores(all_words, answer_words)

    resp_scores = response_scores.copy()
    ans_scores = answer_scores.copy()
    for idx in range(len(response_scores)):
        response_scores[idx] = response_scores[idx][0]
        answer_scores[idx] = answer_scores[idx][0]
    score = np.dot(response_scores, answer_scores) / (np.linalg.norm(response_scores) * np.linalg.norm(answer_scores))
    return score, resp_scores, ans_scores


def preprocess_tokens(text: str):
    text = text.lower()
    to_remove = stopwords.words('english') + list(string.punctuation)
    tokens = [word for word in word_tokenize(text) if word not in to_remove]
    return tokens


def sentence_similarity_mean_w2v(response: str, answer: str):
    response = preprocess_tokens(response)
    answer = preprocess_tokens(answer)
    response_embeddings = [w2v[word] for word in response if w2v.has_index_for(word)]
    answer_embeddings = [w2v[word] for word in answer if w2v.has_index_for(word)]
    if len(response_embeddings) == 0 or len(answer_embeddings) == 0:
        return 0
    response_vector = np.mean(response_embeddings, axis=0)
    answer_vector = np.mean(answer_embeddings, axis=0)
    return float(
        np.dot(response_vector, answer_vector) / (np.linalg.norm(response_vector) * np.linalg.norm(answer_vector)))

def sentence_similarity_transformer(response: str, answer: str):
    pass
    embeddings = sentence_transformer.encode([response, answer])
    return float(np.dot(embeddings[0],embeddings[1]) / (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])))

def get_similarity_function_by_mode(mode: str):
    if mode == 'bow':
        return lambda str1, str2 : sentence_similarity(str1, str2)[0]
    elif mode == 'w2v':
        return sentence_similarity_mean_w2v
    elif mode == 'transformer':
        return sentence_similarity_transformer
    else: # mode == 'auto'
        return sentence_similarity_mean_w2v


if __name__ == "__main__":
    pass
    print(evaluation_function("flow", "fluid", {"mode": "bow"}))
    #print(evaluation_function("Density, speed, Viscosity, Length", "Density, Velocity, Viscosity, Length", {'keystrings': [{"string": "density"}, {"string": "velocity", "exact_match": False, 'should_contain': False}, {"string": "viscosity"}, {"string": "length"}]}))
    #print(evaluation_function("Molecules are made out of atoms", "Many atoms form a molecule", {'keystrings': [{'string': 'molecule'}, {'string': 'proton', 'exact_match': True}]}))
    #print(evaluation_function("solid, liquid", 'solid, liquid, gas', params={"mode": "bow", "keystrings":[{"string":"solid"}, {"string":"liquid"}, {"string":"gas", "custom_feedback":"What is water's aggregation state when above 100 degrees?"}]}))

# File sizes / Location / Permissions
# Clear everything including nltk. Test with small files.
#
# Confidence score for evaluations of answers, grouped by 'correct'/'incorrect' answers
#

