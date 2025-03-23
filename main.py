import os
import re
from collections import defaultdict
import tkinter as tk
from tkinter import scrolledtext, messagebox
from nltk.stem import PorterStemmer

def load_stopwords(filepath):
    stopwords = set()
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            word = line.strip()
            if word:
                stopwords.add(word.lower())
    print(f"Loaded stopwords: {stopwords}")
    return stopwords

def tokenize(text):
    tokens = re.findall(r'\w+', text)
    print(f"Tokenized text: {tokens}")
    return tokens

def preprocess(text, stopwords, stemmer):
    # Case folding
    text = text.lower()
    print(f"Case-folded text: {text[:100]}...")  # Print first 100 chars for brevity
    # Tokenization
    tokens = tokenize(text)
    # Stopword removal and stemming
    processed = []
    for token in tokens:
        if token not in stopwords:
            stemmed = stemmer.stem(token)
            processed.append(stemmed)
    print(f"Preprocessed tokens: {processed}")
    return processed

class Indexer:
    def __init__(self, abstracts_dir, stopword_file):
        self.abstracts_dir = abstracts_dir
        self.stopwords = load_stopwords(stopword_file)
        self.stemmer = PorterStemmer()
        self.inverted_index = defaultdict(set)
        self.positional_index = defaultdict(lambda: defaultdict(list))
        self.documents = {}
    
    def build_indexes(self):
        print("Starting index build...")
        for filename in os.listdir(self.abstracts_dir):
            filepath = os.path.join(self.abstracts_dir, filename)
            if os.path.isfile(filepath):
                # Remove extension and extra spaces from doc_id.
                doc_id = filename.replace('.txt', '').strip()
                try:
                    with open(filepath, 'r', encoding='utf8') as f:
                        text = f.read()
                except UnicodeDecodeError:
                    with open(filepath, 'r', encoding='ISO-8859-1') as f:
                        text = f.read()
                
                print(f"\nProcessing document: {doc_id}")
                self.documents[doc_id] = text
                # Debug: Print a snippet of the raw text
                print(f"Raw text snippet: {text[:100]}...")
                tokens = preprocess(text, self.stopwords, self.stemmer)
                # Debug: Print final tokens for this document
                print(f"Final tokens for document {doc_id}: {tokens}")
                for pos, term in enumerate(tokens):
                    self.inverted_index[term].add(doc_id)
                    self.positional_index[term][doc_id].append(pos)
        print("Indexes built successfully.")
    
    def get_posting_list(self, term):
        term = self.stemmer.stem(term.lower())
        return self.inverted_index.get(term, set())
    
    def get_positions(self, term, doc_id):
        term = self.stemmer.stem(term.lower())
        return self.positional_index.get(term, {}).get(doc_id, [])
    
    def all_docs(self):
        return set(self.documents.keys())

class BooleanQueryProcessor:
    def __init__(self, indexer):
        self.indexer = indexer
        self.all_docs = indexer.all_docs()
    
    def process_query(self, query):
        query = query.strip()
        print(f"\nProcessing query: {query}")
        
        # Check for proximity query syntax first.
        if '/' in query:
            return self.proximity_query(query)
        
        # If the query is enclosed in double quotes, treat it as a phrase query.
        if query.startswith('"') and query.endswith('"'):
            phrase = query[1:-1].strip()  # Remove quotes
            tokens = phrase.split()
            return self.process_phrase_query_all(tokens)
        
        # Otherwise, process as a normal Boolean query.
        tokens = query.split()
        if len(tokens) == 0:
            return set()
        
        #Enforce at most 3 index terms for Boolean queries:
        non_operator_terms = [token for token in tokens if token.upper() not in {"AND", "OR", "NOT"}]
        if len(non_operator_terms) > 3:
            raise ValueError("Error: Boolean query must contain at most three index terms.")
        
        cost = 0  # For cost evaluation
        result = None
        operator = None
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if token.upper() in ("AND", "OR"):
                operator = token.upper()
                print(f"Current operator: {operator}")
            elif token.upper() == "NOT":
                idx += 1
                if idx >= len(tokens):
                    raise ValueError("Invalid query: NOT must be followed by a term")
                term = tokens[idx]
                term_posting = self.all_docs - self.indexer.get_posting_list(term)
                cost += len(term_posting)
                if result is None:
                    result = term_posting
                    print(f"Initial result set (NOT): {term_posting}")
                else:
                    if operator == "AND":
                        cost += len(result) + len(term_posting)
                        result = result.intersection(term_posting)
                        print(f"Intersection result (NOT): {result}")
                    elif operator == "OR":
                        cost += len(result) + len(term_posting)
                        result = result.union(term_posting)
                        print(f"Union result (NOT): {result}")
            else:
                term_posting = self.indexer.get_posting_list(token)
                cost += len(term_posting)
                if result is None:
                    result = term_posting
                    print(f"Initial result set: {term_posting}")
                else:
                    if operator == "AND":
                        cost += len(result) + len(term_posting)
                        result = result.intersection(term_posting)
                        print(f"Intersection result: {result}")
                    elif operator == "OR":
                        cost += len(result) + len(term_posting)
                        result = result.union(term_posting)
                        print(f"Union result: {result}")
                    else:
                        # Default to AND if no explicit operator is provided.
                        cost += len(result) + len(term_posting)
                        result = result.intersection(term_posting)
                        print(f"Default (AND) intersection result: {result}")
            idx += 1
        print(f"Query cost: {cost}")
        return result if result is not None else set()
    
    def process_phrase_query_all(self, tokens):
        """
        Process a phrase query for multiple tokens.
        Returns documents where tokens appear consecutively.
        """
        if not tokens:
            return set()
        
        # Get posting list for the first term.
        result_docs = self.indexer.get_posting_list(tokens[0])
        # For each subsequent term, narrow down the candidate docs.
        for i in range(1, len(tokens)):
            term = tokens[i]
            current_postings = self.indexer.get_posting_list(term)
            result_docs = result_docs.intersection(current_postings)
        
        # For each candidate doc, verify consecutive positions.
        final_docs = set()
        for doc in result_docs:
            pos_list = self.indexer.get_positions(tokens[0], doc)
            for pos in pos_list:
                match = True
                for i in range(1, len(tokens)):
                    expected_pos = pos + i
                    positions = self.indexer.get_positions(tokens[i], doc)
                    if expected_pos not in positions:
                        match = False
                        break
                if match:
                    final_docs.add(doc)
                    break
        print(f"Phrase query result for tokens {tokens}: {final_docs}")
        return final_docs

    def proximity_query(self, query):
        try:
            terms_part, k_str = query.split('/')
            k = int(k_str.strip())
        except Exception as e:
            print("Error parsing proximity query. Ensure it is in the form: term1 term2 / k")
            return set()
        terms = terms_part.strip().split()
        if len(terms) != 2:
            print("Proximity query currently supports exactly two terms.")
            return set()
        term1, term2 = terms
        docs1 = self.indexer.get_posting_list(term1)
        docs2 = self.indexer.get_posting_list(term2)
        candidate_docs = docs1.intersection(docs2)
        result_docs = set()
        for doc in candidate_docs:
            pos_list1 = self.indexer.get_positions(term1, doc)
            pos_list2 = self.indexer.get_positions(term2, doc)
            i, j = 0, 0
            while i < len(pos_list1) and j < len(pos_list2):
                pos1 = pos_list1[i]
                pos2 = pos_list2[j]
                if abs(pos1 - pos2) - 1 <= k:
                    result_docs.add(doc)
                    break
                if pos1 < pos2:
                    i += 1
                else:
                    j += 1
        return result_docs

def load_gold_queries(gold_file):
    gold_queries = []
    with open(gold_file, 'r', encoding='utf8') as f:
        content = f.read()
    blocks = content.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        query_line = lines[0]
        result_line = lines[1]
        query_match = re.search(r"Example Query:\s*(.+)", query_line)
        result_match = re.search(r"Result-Set:\s*(.+)", result_line)
        if query_match and result_match:
            query = query_match.group(1).strip()
            result_str = result_match.group(1).strip()
            expected_set = set([doc.strip().replace('.txt', '') for doc in result_str.split(',') if doc.strip()])
            gold_queries.append((query, expected_set))
    return gold_queries

def run_gold_standard_tests(query_processor, gold_file):
    print("\nRunning Gold Standard Tests:")
    gold_queries = load_gold_queries(gold_file)
    total = len(gold_queries)
    passed = 0
    for query, expected in gold_queries:
        result = query_processor.process_query(query)
        if result == expected:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
        print(f"\nQuery: {query}")
        print(f"Expected: {sorted(expected)}")
        print(f"Got:      {sorted(result)}")
        print(f"Status: {status}")
    print(f"\nGold Standard Test Results: {passed}/{total} queries passed.")

class IRGUI:
    def __init__(self, master, query_processor):
        self.master = master
        self.query_processor = query_processor
        master.title("Boolean Information Retrieval System")

        self.label = tk.Label(master, text="Enter your Boolean query below:")
        self.label.pack(pady=5)

        self.query_entry = tk.Entry(master, width=80)
        self.query_entry.pack(padx=10, pady=5)

        self.search_button = tk.Button(master, text="Search", command=self.execute_query)
        self.search_button.pack(pady=5)

        self.result_area = scrolledtext.ScrolledText(master, width=80, height=20)
        self.result_area.pack(padx=10, pady=10)

        self.gold_button = tk.Button(master, text="Run Gold Standard Tests", command=self.run_gold_tests)
        self.gold_button.pack(pady=5)

        self.exit_button = tk.Button(master, text="Exit", command=master.quit)
        self.exit_button.pack(pady=5)

    def execute_query(self):
        query = self.query_entry.get().strip()
        if not query:
            messagebox.showwarning("Warning", "Please enter a query.")
            return
        try:
            result = self.query_processor.process_query(query)
            self.result_area.delete(1.0, tk.END)
            if result:
                result_list = sorted(result)
                result_text = "Result-Set: " + ", ".join(result_list)
            else:
                result_text = "No documents matched the query."
            self.result_area.insert(tk.END, result_text)
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def run_gold_tests(self):
        gold_file = "Gold Query-Set Boolean Queries.txt"
        gold_queries = load_gold_queries(gold_file)
        output = ""
        for query, expected in gold_queries:
            result = self.query_processor.process_query(query)
            status = "PASS" if result == expected else "FAIL"
            output += f"Query: {query}\nExpected: {sorted(expected)}\nGot:      {sorted(result)}\nStatus: {status}\n\n"
        result_window = tk.Toplevel(self.master)
        result_window.title("Gold Standard Test Results")
        text_area = scrolledtext.ScrolledText(result_window, width=80, height=30)
        text_area.pack(padx=10, pady=10)
        text_area.insert(tk.END, output)

def main():
    abstracts_dir = "Abstracts"
    stopword_file = "Stopword-List.txt"
    gold_file = "Gold Query-Set Boolean Queries.txt"
    
    print("Building indexes...")
    indexer = Indexer(abstracts_dir, stopword_file)
    indexer.build_indexes()
    
    query_processor = BooleanQueryProcessor(indexer)
    
    run_gold_standard_tests(query_processor, gold_file)
    
    root = tk.Tk()
    gui = IRGUI(root, query_processor)
    root.mainloop()

if __name__ == "__main__":
    main()
