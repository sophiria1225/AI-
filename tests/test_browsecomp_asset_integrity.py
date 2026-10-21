import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from download_browsecomp_assets import asset_rows, verify


class PinnedAssetControls(unittest.TestCase):
    def test_reject_hash_size_and_path_changes_for_lfs_and_git_objects(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'asset';p.write_bytes(b'abc')
            for method, expected in [('sha256',hashlib.sha256(b'abc').hexdigest()),
                                     ('git_blob_sha1',hashlib.sha1(b'blob 3\0abc').hexdigest())]:
                asset={'size':3,'digest_type':method,'expected_digest':expected}
                self.assertEqual(verify(p,asset)['bytes'],3)
                with self.assertRaises(ValueError):verify(p,{**asset,'size':4})
                with self.assertRaises(ValueError):verify(p,{**asset,'expected_digest':'0'*len(expected)})
        manifest={'datasets':[{'identifier':'Tevatron/browsecomp-plus','revision':'fixed',
                               'files':[{'path':'../escape.parquet','size':3,'oid':'a'*40}]}]}
        with self.assertRaises(ValueError):asset_rows(manifest,'qa')
