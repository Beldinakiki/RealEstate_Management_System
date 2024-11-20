import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity

class RentalRecommender:
    def __init__(self, csv_path='rent_apts.csv'):
        self.csv_path = csv_path
        self.df = None
        self.scaler = StandardScaler()
        self.features_scaled = None
        self.load_and_prepare_data()

    def load_and_prepare_data(self):
        """Load and preprocess the rental dataset"""
        try:
            # Read CSV file
            self.df = pd.read_csv(self.csv_path)
            
            # Clean price column - Extract numeric value from price string
            self.df['Price'] = self.df['Price'].apply(lambda x: float(str(x).replace('KSh ', '').replace(',', '')) if pd.notnull(x) else np.nan)
            
            # Convert columns to numeric, replacing invalid values with NaN
            self.df['Bedrooms'] = pd.to_numeric(self.df['Bedrooms'], errors='coerce')
            self.df['Bathrooms'] = pd.to_numeric(self.df['Bathrooms'], errors='coerce')
            self.df['sq_mtrs'] = pd.to_numeric(self.df['sq_mtrs'], errors='coerce')
            
            # Fill NaN values with median values
            self.df['Bedrooms'] = self.df['Bedrooms'].fillna(self.df['Bedrooms'].median())
            self.df['Bathrooms'] = self.df['Bathrooms'].fillna(self.df['Bathrooms'].median())
            self.df['sq_mtrs'] = self.df['sq_mtrs'].fillna(self.df['sq_mtrs'].median())
            self.df['Price'] = self.df['Price'].fillna(self.df['Price'].median())
            
            # Create and scale features
            features = self.df[['Price', 'Bedrooms', 'Bathrooms', 'sq_mtrs']].values
            self.features_scaled = self.scaler.fit_transform(features)
            
        except Exception as e:
            print(f"Error loading data: {str(e)}")
            raise

    def get_recommendations(self, location=None, price=None, bedrooms=None, bathrooms=None, num_recommendations=5):
        """Get property recommendations based on input criteria"""
        try:
            # Use median values if not provided
            if price is None:
                price = self.df['Price'].median()
            if bedrooms is None:
                bedrooms = self.df['Bedrooms'].median()
            if bathrooms is None:
                bathrooms = self.df['Bathrooms'].median()

            # Create query point
            query = np.array([[
                price,
                bedrooms,
                bathrooms,
                self.df['sq_mtrs'].median()  # Use median sq_mtrs as default
            ]])
            
            # Scale query
            query_scaled = self.scaler.transform(query)
            
            # Calculate similarities
            similarities = cosine_similarity(query_scaled, self.features_scaled)
            
            # Get top similar properties
            similar_indices = similarities[0].argsort()[-num_recommendations:][::-1]
            
            # Filter by location if provided
            recommendations = self.df.iloc[similar_indices].copy()
            if location:
                location = location.lower()
                location_mask = recommendations['Neighborhood'].str.lower().str.contains(location, na=False)
                if location_mask.any():
                    recommendations = recommendations[location_mask]
            
            # Add similarity scores
            recommendations['similarity_score'] = similarities[0][similar_indices]
            
            # Format the output
            return self._format_recommendations(recommendations)
            
        except Exception as e:
            print(f"Error getting recommendations: {str(e)}")
            return []

    def _format_recommendations(self, recommendations):
        """Format recommendations for output"""
        formatted = []
        for _, row in recommendations.iterrows():
            formatted.append({
                'agency': row['Agency'],
                'neighborhood': row['Neighborhood'],
                'price': float(row['Price']),
                'bedrooms': int(row['Bedrooms']),
                'bathrooms': int(row['Bathrooms']),
                'sq_mtrs': float(row['sq_mtrs']),
                'similarity_score': round(float(row['similarity_score'] * 100), 2),
                'link': row['link']
            })
        return formatted

    def get_price_range(self, neighborhood):
        """Get price statistics for a neighborhood"""
        if neighborhood:
            neighborhood_data = self.df[
                self.df['Neighborhood'].str.lower().str.contains(neighborhood.lower(), na=False)
            ]['Price']
            if not neighborhood_data.empty:
                return {
                    'min_price': float(neighborhood_data.min()),
                    'max_price': float(neighborhood_data.max()),
                    'avg_price': float(neighborhood_data.mean()),
                    'median_price': float(neighborhood_data.median())
                }
        return None