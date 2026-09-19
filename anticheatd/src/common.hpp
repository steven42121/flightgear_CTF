#pragma once
#include <string>
#include <vector>
#include <sstream>
#include <iomanip>
#include <cstdint>

#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#else
#include <openssl/evp.h>
#include <openssl/hmac.h>
#endif

/**
 * SHA-256 hash of input data
 */
inline std::string sha256(const std::string& data) {
    std::string result(64, '0');
    
#ifdef _WIN32
    HBCRYPT hash = nullptr;
    HCSPROV prov = nullptr;
    BCRYPT_ALG_HANDLE alg = nullptr;
    
    BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, nullptr, 0);
    BCryptHashData(alg, (BYTE*)data.c_str(), data.size(), 0);
    BCryptFinishHash(alg, (BYTE*)result.data(), 64, 0);
    BCryptCloseAlgorithmProvider(alg, 0);
#else
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len = 0;
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr);
    EVP_DigestUpdate(ctx, data.c_str(), data.size());
    EVP_DigestFinal_ex(ctx, hash, &hash_len);
    EVP_MD_CTX_free(ctx);
    
    for (unsigned int i = 0; i < hash_len; ++i)
        sprintf(&result[i*2], "%02x", hash[i]);
#endif
    
    return result;
}

/**
 * HMAC-SHA256 of key and message
 */
inline std::string hmac_sha256(const std::string& key, const std::string& message) {
    std::string result(64, '0');
    
#ifdef _WIN32
    HBCRYPT key_handle = nullptr;
    BCryptCreateHash(BCRYPT_SHA256_ALGORITHM, 
                     (BYTE*)key.c_str(), key.size(), 
                     nullptr, 0, 0, &key_handle);
    BCryptHashData(key_handle, (BYTE*)message.c_str(), message.size(), 0);
    BCryptFinishHash(key_handle, (BYTE*)result.data(), 64, 0);
    BCryptDestroyHash(key_handle);
#else
    unsigned char* mac = HMAC(EVP_sha256(), 
                              key.c_str(), key.size(),
                              (const unsigned char*)message.c_str(), message.size(),
                              nullptr, nullptr);
    if (mac) {
        for (int i = 0; i < 32; ++i)
            sprintf(&result[i*2], "%02x", mac[i]);
    }
#endif
    
    return result;
}

/**
 * Convert bytes to hex string
 */
inline std::string bytes_to_hex(const uint8_t* bytes, size_t len) {
    std::ostringstream oss;
    for (size_t i = 0; i < len; ++i)
        oss << std::hex << std::setw(2) << std::setfill('0') << (int)bytes[i];
    return oss.str();
}
