"""M2Crypto wrapper for OpenSSL S/MIME API.

Copyright (c) 2000 Ng Pheng Siong. All rights reserved."""

RCS_id='$Id: SMIME.py,v 1.1 2000/04/01 14:48:32 ngps Exp $'

import BIO, EVP, X509, Err
import M2Crypto
m2=M2Crypto


PKCS7_TEXT	    = m2.PKCS7_TEXT
PKCS7_NOCERTS	= m2.PKCS7_NOCERTS
PKCS7_NOSIGS	= m2.PKCS7_NOSIGS
PKCS7_NOCHAIN	= m2.PKCS7_NOCHAIN
PKCS7_NOINTERN	= m2.PKCS7_NOINTERN
PKCS7_NOVERIFY	= m2.PKCS7_NOVERIFY
PKCS7_DETACHED	= m2.PKCS7_DETACHED
PKCS7_BINARY	= m2.PKCS7_BINARY
PKCS7_NOATTR	= m2.PKCS7_NOATTR


class PKCS7:
    def __init__(self, pkcs7=None, _pyfree=0):
        if pkcs7 is not None:
            self.pkcs7 = pkcs7
            self._pyfree = _pyfree
        else:
            self.pkcs7 = m2.pkcs7_new()
            self._pyfree = 1

    def __del__(self):
        if self._pyfree:
            m2.pkcs7_free(self.pkcs7)

    def _ptr(self):
        return self.pkcs7


def load_pkcs7(p7file):
    bio = m2.bio_new_file(p7file, 'r')
    if bio is None:
        raise Err.get_error()
    p7_ptr, bio_ptr = m2.smime_read_pkcs7(bio)
    m2.bio_free(bio)
    if p7_ptr is None:
        raise Err.get_error()
    if bio_ptr is None:
        return PKCS7(p7_ptr, 1), None
    else:
        #return PKCS7(p7_ptr, 1), BIO.MemoryBuffer(bio_ptr, 1)
        return PKCS7(p7_ptr, 1), BIO.BIO(bio_ptr, 1)
    
            
class Cipher:
    """This is an EVP_CIPHER wrapper minus all the frills of M2Crypto.EVP.Cipher."""
    def __init__(self, algo):
        cipher = getattr(m2, algo)
        if not cipher:
            raise ValueError, ('unknown cipher', algo)
        self.cipher = cipher()

    def _ptr(self):
        return self.cipher


class SMIME_Error(Exception):
    pass


class SMIME:
    def load_key(self, keyfile, certfile=None):
        if certfile is None:
            certfile = keyfile
        self.pkey = EVP.load_key(keyfile)
        self.x509 = X509.load_cert(certfile)

    def set_x509_stack(self, stack):
        assert isinstance(stack, X509.X509_Stack)
        self.x509_stack = stack

    def set_x509_store(self, store):
        assert isinstance(store, X509.X509_Store)
        self.x509_store = store

    def set_cipher(self, cipher):
        assert isinstance(cipher, Cipher)
        self.cipher = cipher

    def unset_key(self):
        del self.pkey
        del self.x509

    def unset_x509_stack(self):
        del self.x509_stack

    def unset_x509_store(self):
        del self.x509_store

    def unset_cipher(self):
        del self.cipher

    def encrypt(self, data_bio, flags=0):
        if not hasattr(self, 'cipher'):
            raise SMIME_Error, 'no cipher: use set_cipher()'
        if not hasattr(self, 'x509_stack'):
            raise SMIME_Error, 'no recipient certs: use set_x509_stack()'
        pkcs7 = m2.pkcs7_encrypt(self.x509_stack._ptr(), data_bio._ptr(), self.cipher._ptr(), flags)
        if pkcs7 is None:
            raise SMIME_Error, Err.get_error()
        return PKCS7(pkcs7, 1)

    def decrypt(self, pkcs7, flags=0):
        if not hasattr(self, 'pkey'):
            raise SMIME_Error, 'no private key: use load_key()'
        if not hasattr(self, 'x509'):
            raise SMIME_Error, 'no certificate: load_key() used incorrectly?'
        blob = m2.pkcs7_decrypt(pkcs7._ptr(), self.pkey._ptr(), self.x509._ptr(), flags)
        if blob is None:
            raise SMIME_Error, Err.get_error()
        return blob

    def sign(self, data_bio, flags=0):
        if not hasattr(self, 'pkey'):
            raise SMIME_Error, 'no private key: use load_key()'
        if hasattr(self, 'x509_stack'):
            pkcs7 = m2.pkcs7_sign1(self.x509._ptr(), self.pkey._ptr(), 
                self.x509_stack._ptr(), data_bio._ptr(), flags)
            if pkcs7 is None:
                raise SMIME_Error, Err.get_error()
            return PKCS7(pkcs7, 1)
        else:
            pkcs7 = m2.pkcs7_sign0(self.x509._ptr(), self.pkey._ptr(), 
                data_bio._ptr(), flags)
            if pkcs7 is None:
                raise SMIME_Error, Err.get_error()
            return PKCS7(pkcs7, 1)

    def verify(self, pkcs7, data_bio=None, flags=0):
        if not hasattr(self, 'x509_stack'):
            raise SMIME_Error, 'no signer certs: use set_x509_stack()'
        if not hasattr(self, 'x509_store'):
            raise SMIME_Error, 'no x509 cert store: use set_x509_store()'
        assert isinstance(pkcs7, PKCS7), 'pkcs7 not an instance of PKCS7'
        p7 = pkcs7._ptr()
        if data_bio is None:
            blob = m2.pkcs7_verify0(p7, self.x509_stack._ptr(), self.x509_store._ptr(), flags)
        else:
            blob = m2.pkcs7_verify1(p7, self.x509_stack._ptr(), self.x509_store._ptr(), data_bio._ptr(), flags)
        if blob is None:
                raise SMIME_Error, Err.get_error()
        return blob

    def save_certs(self, savefile):
        pass

    def write(self, out_bio, pkcs7, data_bio=None, flags=0):
        assert isinstance(pkcs7, PKCS7)
        if data_bio is None:
            return m2.smime_write_pkcs7(out_bio._ptr(), pkcs7._ptr(), flags)
        else:
            return m2.smime_write_pkcs7_multi(out_bio._ptr(), pkcs7._ptr(), data_bio._ptr(), flags)

