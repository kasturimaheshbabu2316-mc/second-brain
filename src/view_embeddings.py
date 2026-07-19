import os
import sys
import pickle

PKL_PATH = os.path.join("data", "embeddings.pkl")

def main():
    if not os.path.exists(PKL_PATH):
        print(f"Error: Pickle file '{PKL_PATH}' does not exist. Please run embeddings script first.")
        sys.exit(1)
        
    try:
        with open(PKL_PATH, "rb") as f:
            data = pickle.load(f)
    except Exception as e:
        print(f"Error loading pickle file: {e}")
        sys.exit(1)
        
    print(f"=== Embeddings Cache Content ({PKL_PATH}) ===")
    print(f"Total notes stored: {len(data)}\n")
    print(f"{'Note Filepath':<70} | {'Dimensions':<10} | {'Vector Preview (First 5 dimensions)'}")
    print("-" * 125)
    
    for filepath, info in data.items():
        embedding = info.get("embedding", [])
        dims = len(embedding)
        preview = ", ".join(f"{v:.4f}" for v in embedding[:5])
        if dims > 5:
            preview += ", ..."
        
        # Display short basename or relative path to avoid long lines
        rel_path = os.path.relpath(filepath)
        print(f"{rel_path:<70} | {dims:<10} | [{preview}]")

if __name__ == "__main__":
    main()
